import asyncio
import re
from datetime import datetime, timedelta
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, EmailStr, Field

from core import db, now_utc
from services.email_service import CONSOLE_MODE
from services.storage import LOCAL_DIR
from rbac import PERMISSIONS, ROLE_PERMS, ROLES, STAFF_ROLES, UNMASKED_CONTACT_ROLES
from routes.config import Cycle, oid
from routes.otp import _mask
from security import User, audit, current_user, err, hash_password, require, require_candidate, \
    require_verified_candidate, revoke_sessions, temp_password

router = APIRouter(prefix="/api", tags=["administration"])

StaffRole = Literal[tuple(STAFF_ROLES)]


class CreateUserIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    role: StaffRole


class UpdateUserIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    role: Optional[StaffRole] = None
    status: Optional[Literal["active", "disabled"]] = None


def _user_out(d: dict) -> dict:
    u = User.from_mongo(d)
    return u.model_dump(exclude={"password_hash"}) | {"role_label": ROLES[u.role]["label"]}


@router.get("/admin/roles")
async def roles(_: User = Depends(require("roles.read"))):
    return {"roles": [{"key": k, **v, "permissions": ROLE_PERMS[k]} for k, v in ROLES.items()],
            "permissions": [{"key": k, "description": v} for k, v in PERMISSIONS.items()]}


@router.get("/admin/users")
async def list_users(role: Optional[str] = None, q: Optional[str] = None, _: User = Depends(require("users.manage"))):
    f: dict = {"role": role} if role else {"role": {"$ne": "candidate"}}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        f["$or"] = [{"name": rx}, {"email": rx}]
    return [_user_out(d) async for d in db.users.find(f).sort("created_at", 1).limit(500)]


@router.post("/admin/users")
async def create_user(body: CreateUserIn, request: Request, actor: User = Depends(require("users.manage"))):
    email = str(body.email).lower()
    if await db.users.find_one({"email": email}):
        raise err(409, "email_exists", "A user with this email already exists")
    pw = temp_password()
    u = User(email=email, name=body.name.strip(), role=body.role, password_hash=hash_password(pw),
             must_change_password=True, created_by=actor.email)
    res = await db.users.insert_one(u.to_mongo())
    u.id = str(res.inserted_id)
    await audit(request, actor, "user.created", "user", u.id, after={"email": email, "name": u.name, "role": u.role})
    return {"user": _user_out(u.to_mongo() | {"_id": res.inserted_id}), "temporary_password": pw}


@router.patch("/admin/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserIn, request: Request, actor: User = Depends(require("users.manage"))):
    _id = oid(user_id)
    before = await db.users.find_one({"_id": _id})
    if not before or before["role"] == "candidate":
        raise err(404, "not_found", "Staff user not found")
    changes = body.model_dump(exclude_none=True)
    if user_id == actor.id and ({"role", "status"} & changes.keys()):
        raise err(409, "self_change", "You cannot change your own role or status")
    if not changes:
        return _user_out(before)
    await db.users.update_one({"_id": _id}, {"$set": changes})
    after = await db.users.find_one({"_id": _id})
    if changes.get("status") == "disabled" or "role" in changes:
        await revoke_sessions(user_id)
    await audit(request, actor, "user.updated", "user", user_id,
                before={k: before.get(k) for k in changes}, after={k: after.get(k) for k in changes})
    return _user_out(after)


@router.post("/admin/users/{user_id}/reset-password")
async def reset_user_password(user_id: str, request: Request, actor: User = Depends(require("users.manage"))):
    _id = oid(user_id)
    u = await db.users.find_one({"_id": _id})
    if not u or u["role"] == "candidate":
        raise err(404, "not_found", "Staff user not found")
    pw = temp_password()
    await db.users.update_one({"_id": _id}, {"$set": {"password_hash": hash_password(pw), "must_change_password": True}})
    await revoke_sessions(user_id)
    await audit(request, actor, "user.password_reset", "user", user_id, after={"email": u["email"]})
    return {"temporary_password": pw}


@router.get("/admin/candidates")
async def list_candidates(status: Optional[str] = None, q: Optional[str] = None,
                          viewer: User = Depends(require("candidates.read"))):
    f: dict = {"role": "candidate"}
    if status:
        f["identity_status"] = status
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        f["$or"] = [{"name": rx}, {"email": rx}, {"candidate_ref": rx}]
    out = []
    async for d in db.users.find(f).sort("created_at", -1).limit(500):
        u = User.from_mongo(d)
        row = u.model_dump(include={"id", "candidate_ref", "name", "email", "mobile", "state", "city",
                                    "identity_status", "email_verified_at", "whatsapp_verified_at", "created_at"})
        if viewer.role not in UNMASKED_CONTACT_ROLES:
            row["email"], row["mobile"] = _mask("email", u.email), _mask("whatsapp", u.mobile or "+0000000000")
        out.append(row)
    return out


@router.get("/audit")
async def audit_log(action: Optional[str] = None, entity_type: Optional[str] = None, actor: Optional[str] = None,
                    outcome: Optional[str] = None, date_from: Optional[datetime] = None,
                    date_to: Optional[datetime] = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                    _: User = Depends(require("audit.read"))):
    f: dict = {}
    if action:
        f["action"] = {"$regex": f"^{re.escape(action)}"}
    if entity_type:
        f["entity_type"] = entity_type
    if outcome:
        f["outcome"] = outcome
    if actor:
        f["actor.email"] = {"$regex": re.escape(actor), "$options": "i"}
    if date_from or date_to:
        f["at"] = {k: v for k, v in (("$gte", date_from), ("$lte", date_to)) if v}
    total = await db.audit_log.count_documents(f)
    items = []
    async for d in db.audit_log.find(f).sort("at", -1).skip((page - 1) * page_size).limit(page_size):
        d["id"] = str(d.pop("_id"))
        items.append(d)
    return {"total": total, "page": page, "page_size": page_size, "items": items,
            "actions": sorted(await db.audit_log.distinct("action")),
            "entity_types": sorted(t for t in await db.audit_log.distinct("entity_type") if t)}


MODULES = {
    "super_admin": [("part-a", "Part A dashboard", 1), ("applications", "Applications", 1), ("users", "Users & roles", 1), ("cycles", "Admission cycles", 1), ("programs", "Programs & seats", 1),
                    ("policies", "Policies", 1), ("audit", "Audit log", 1)],
    "admissions_operator": [("candidates", "Candidates", 1), ("applications", "Applications", 1), ("part-a", "Part A dashboard", 1),
                            ("allotments", "Allotment batches", 4)],
    "document_verifier": [("verification", "Document verification worklists", 1)],
    "panelist": [("scoring", "Assigned GA/PI sessions", 1)],
    "interview_coordinator": [("interviews", "Locations, sessions & attendance", 1), ("evaluations", "Evaluation & slot reports", 1)],
    "accounts_operator": [("payments", "Payments & refunds", 5), ("reconciliation", "Reconciliation", 5)],
    "result_approver": [("results", "Result versions", 1), ("evaluations", "Evaluation reports", 1)],
    "auditor": [("audit", "Audit log", 1), ("candidates", "Candidates (masked)", 1), ("reports", "Reports", 5)],
}


@router.get("/dashboard")
async def dashboard(user: User = Depends(current_user)):
    if user.role == "candidate":
        raise err(403, "forbidden", "Staff dashboard only")
    cycle = Cycle.from_mongo(await db.cycles.find_one({"status": "active"}))
    progs = await db.programs.find({"cycle_id": cycle.id, "status": "active"}).to_list(200) if cycle else []
    kpis = [{"label": "Active cycle", "value": cycle.code if cycle else "None"},
            {"label": "Programs", "value": len(progs)},
            {"label": "Total seats", "value": sum(p["seat_capacity"] for p in progs)}]
    if user.role in ("super_admin", "admissions_operator", "auditor"):
        verified, partial, registered = await asyncio.gather(
            db.users.count_documents({"role": "candidate", "identity_status": "verified"}),
            db.users.count_documents({"role": "candidate", "identity_status": "partially_verified"}),
            db.users.count_documents({"role": "candidate", "identity_status": "registered"}),
        )
        kpis.extend([
            {"label": "Candidates · verified", "value": verified},
            {"label": "Candidates · partially verified", "value": partial},
            {"label": "Candidates · registered", "value": registered},
        ])
    extra = []
    if user.role == "super_admin":
        extra.append(db.users.count_documents({"role": {"$ne": "candidate"}}))
    if user.role in ("super_admin", "auditor"):
        since = now_utc() - timedelta(hours=24)
        extra.extend([
            db.audit_log.count_documents({"at": {"$gte": since}}),
            db.audit_log.count_documents({"at": {"$gte": since}, "outcome": "denied"}),
        ])
    if user.role == "accounts_operator":
        extra.append(db.payment_orders.count_documents({"status": "paid"}))
    if extra:
        counts = await asyncio.gather(*extra)
        labels = []
        if user.role == "super_admin":
            labels.append("Staff users")
        if user.role in ("super_admin", "auditor"):
            labels.extend(["Audit events · 24h", "Denied requests · 24h"])
        if user.role == "accounts_operator":
            labels.append("Paid orders (POC)")
        kpis.extend({"label": label, "value": value} for label, value in zip(labels, counts))
    try:
        await db.command("ping")
        mongo = "ok"
    except Exception:
        mongo = "down"
    return {"role": user.role, "role_label": ROLES[user.role]["label"], "kpis": kpis,
            "health": {"mongo": mongo, "storage": "local" if LOCAL_DIR else "remote", "email": "console" if CONSOLE_MODE else "live"},
            "modules": [{"key": k, "title": t, "phase": p, "ready": p == 1 or k == "reports"} for k, t, p in MODULES[user.role]]}


PLACEHOLDERS = {
    "reports": ("reports.read", 5),
}


def _placeholder(module: str, perm: str, phase: int):
    async def handler(_: User = Depends(require(perm))):
        return {"module": module, "items": [], "message": f"This module arrives in Phase {phase}."}
    return handler


for _m, (_perm, _phase) in PLACEHOLDERS.items():
    router.add_api_route(f"/modules/{_m}", _placeholder(_m, _perm, _phase), methods=["GET"], tags=["modules"])
