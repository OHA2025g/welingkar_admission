import os
import secrets
from datetime import date, datetime, timedelta
from typing import Any, Optional

import bcrypt
import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, Request, Response
from pydantic import Field

from core import BaseDocument, client_ip, db, now_utc
from rbac import ROLE_PERMS, ROLES, idle_for

COOKIE = "ws_session"
ALG = "HS256"
ABS_HOURS = 12


class User(BaseDocument):
    email: str
    name: str
    role: str
    password_hash: str
    status: str = "active"
    mobile: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    candidate_ref: Optional[str] = None
    identity_status: Optional[str] = None
    email_verified_at: Optional[datetime] = None
    whatsapp_verified_at: Optional[datetime] = None
    must_change_password: bool = False
    created_at: datetime = Field(default_factory=now_utc)
    created_by: Optional[str] = None
    last_login_at: Optional[datetime] = None

    def public(self) -> dict:
        d = self.model_dump(exclude={"password_hash"})
        d.update(role_label=ROLES[self.role]["label"], home=ROLES[self.role]["home"],
                 permissions=ROLE_PERMS[self.role], idle_minutes=idle_for(self.role))
        return d


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except ValueError:
        return False


def temp_password() -> str:
    return f"Ws-{secrets.token_urlsafe(6)}9a"


def err(status: int, code: str, message: str, **extra):
    return HTTPException(status, {"code": code, "message": message, **extra})


async def open_session(user: User, request: Request, response: Response) -> str:
    sid, now = secrets.token_urlsafe(24), now_utc()
    await db.sessions.insert_one({
        "sid": sid, "user_id": user.id, "role": user.role, "idle_minutes": idle_for(user.role),
        "created_at": now, "last_seen_at": now, "expires_at": now + timedelta(hours=ABS_HOURS),
        "revoked_at": None, "ip": client_ip(request)})
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {"last_login_at": now}})
    token = jwt.encode({"sub": user.id, "sid": sid, "role": user.role, "type": "access",
                        "exp": now + timedelta(hours=ABS_HOURS)}, os.environ["JWT_SECRET"], algorithm=ALG)
    response.set_cookie(COOKIE, token, httponly=True, secure=os.environ.get("COOKIE_SECURE", "true") != "false", samesite="lax",
                        max_age=ABS_HOURS * 3600, path="/")
    return token


async def revoke_sessions(user_id: str, sid: Optional[str] = None):
    q = {"user_id": user_id, "revoked_at": None}
    if sid:
        q["sid"] = sid
    await db.sessions.update_many(q, {"$set": {"revoked_at": now_utc()}})


async def current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
    if not token:
        raise err(401, "not_authenticated", "Please sign in")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[ALG])
    except jwt.ExpiredSignatureError:
        raise err(401, "session_expired", "Your session has expired. Please sign in again.")
    except jwt.InvalidTokenError:
        raise err(401, "invalid_session", "Invalid session")
    s = await db.sessions.find_one({"sid": payload.get("sid"), "revoked_at": None})
    if not s:
        raise err(401, "session_revoked", "Session ended. Please sign in again.")
    now = now_utc()
    if now - s["last_seen_at"] > timedelta(minutes=s["idle_minutes"]):
        await db.sessions.update_one({"_id": s["_id"]}, {"$set": {"revoked_at": now, "revoked_reason": "idle"}})
        raise err(401, "session_expired", f"Signed out after {s['idle_minutes']} minutes of inactivity.")
    user = User.from_mongo(await db.users.find_one({"_id": ObjectId(payload["sub"])}))
    if not user or user.status != "active":
        raise err(401, "account_inactive", "Account is not active")
    if now - s["last_seen_at"] > timedelta(seconds=45):
        await db.sessions.update_one({"_id": s["_id"]}, {"$set": {"last_seen_at": now}})
    request.state.user, request.state.sid = user, s["sid"]
    return user


def require(*perms: str):
    async def dep(request: Request, user: User = Depends(current_user)) -> User:
        if not all(p in ROLE_PERMS[user.role] for p in perms):
            await audit(request, user, "access.denied", "endpoint", f"{request.method} {request.url.path}",
                        after={"required": list(perms)}, outcome="denied")
            raise err(403, "forbidden", "You do not have access to this resource")
        return user
    return dep


def require_any(*perms: str):
    async def dep(request: Request, user: User = Depends(current_user)) -> User:
        if not any(p in ROLE_PERMS[user.role] for p in perms):
            await audit(request, user, "access.denied", "endpoint", f"{request.method} {request.url.path}",
                        after={"required_any": list(perms)}, outcome="denied")
            raise err(403, "forbidden", "You do not have access to this resource")
        return user
    return dep


async def require_candidate(request: Request, user: User = Depends(current_user)) -> User:
    if user.role != "candidate":
        await audit(request, user, "access.denied", "endpoint", f"{request.method} {request.url.path}",
                    after={"required": ["candidate"]}, outcome="denied")
        raise err(403, "forbidden", "Candidate portal only")
    return user


async def require_verified_candidate(user: User = Depends(require_candidate)) -> User:
    if user.identity_status != "verified":
        raise err(403, "identity_unverified", "Verify both email and WhatsApp to continue")
    return user


def _clean(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items() if k not in ("password_hash", "_id")}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _diff(before: Optional[dict], after: Optional[dict]) -> list[dict]:
    b, a = before or {}, after or {}
    skip = {"updated_at", "version"}
    return [{"field": k, "before": b.get(k), "after": a.get(k)}
            for k in sorted(set(b) | set(a)) if k not in skip and b.get(k) != a.get(k)]


async def audit(request: Request, actor: Optional[User], action: str, entity_type: str, entity_id: Optional[str] = None,
                before: Optional[dict] = None, after: Optional[dict] = None, reason: Optional[str] = None,
                outcome: str = "success", actor_email: Optional[str] = None):
    b, a = _clean(before), _clean(after)
    await db.audit_log.insert_one({
        "at": now_utc(), "action": action, "entity_type": entity_type, "entity_id": entity_id,
        "actor": {"id": actor.id, "email": actor.email, "name": actor.name, "role": actor.role} if actor
        else {"id": None, "email": actor_email, "name": None, "role": "anonymous" if actor_email else "system"},
        "before": b, "after": a, "changes": _diff(b, a) if (b or a) else [], "reason": reason, "outcome": outcome,
        "correlation_id": getattr(request.state, "correlation_id", None) if request else None,
        "ip": client_ip(request) if request else None,
    })
