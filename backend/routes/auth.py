import re
from datetime import timedelta
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core import client_ip, db, now_utc
from routes.otp import OTP_TTL_MIN, _mask, consume_challenge, issue_challenge
from security import (COOKIE, User, audit, current_user, err, hash_password, open_session, require_candidate,
                      revoke_sessions, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_LOGIN_FAILS = 5
LOCK_MINUTES = 15
PRIVILEGED_STAFF = {"super_admin", "accounts_operator", "admissions_operator"}


def normalize_mobile(v: str) -> str:
    v = re.sub(r"[\s\-()]", "", v or "")
    if re.fullmatch(r"[6-9]\d{9}", v):
        v = "+91" + v
    if not re.fullmatch(r"\+[1-9]\d{7,14}", v):
        raise ValueError("Enter a valid mobile number, e.g. 9876543210 or +919876543210")
    return v


def strong(p: str) -> str:
    if len(p) < 8 or not re.search(r"[A-Za-z]", p) or not re.search(r"\d", p):
        raise ValueError("Password must be at least 8 characters with letters and numbers")
    return p


class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    mobile: str
    state: str = Field(min_length=2, max_length=60)
    city: str = Field(min_length=2, max_length=60)
    password: str

    _m = field_validator("mobile")(classmethod(lambda cls, v: normalize_mobile(v)))
    _p = field_validator("password")(classmethod(lambda cls, v: strong(v)))


class ChannelIn(BaseModel):
    channel: Literal["email", "whatsapp"]


class VerifyChannelIn(ChannelIn):
    challenge_id: str
    code: str


class EmailIn(BaseModel):
    email: EmailStr


class OtpCompleteIn(BaseModel):
    challenge_id: str
    code: str


class StaffStepUpIn(BaseModel):
    challenge_id: str
    code: str = Field(min_length=6, max_length=6)


class RecoveryCompleteIn(OtpCompleteIn):
    new_password: str
    _p = field_validator("new_password")(classmethod(lambda cls, v: strong(v)))


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str
    _p = field_validator("new_password")(classmethod(lambda cls, v: strong(v)))


async def _next_candidate_ref() -> str:
    c = await db.counters.find_one_and_update({"_id": "candidate_ref"}, {"$inc": {"seq": 1}}, upsert=True,
                                              return_document=ReturnDocument.AFTER)
    return f"WS-C-26-{c['seq']:05d}"


async def _password_login(body: LoginIn, request: Request, response: Response, staff: bool) -> dict:
    email = body.email.strip().lower()
    ident = f"{client_ip(request)}:{email}"
    att = await db.login_attempts.find_one({"identifier": ident})
    if att and att.get("locked_until") and att["locked_until"] > now_utc():
        mins = int((att["locked_until"] - now_utc()).total_seconds() // 60) + 1
        raise err(429, "locked_out", f"Too many failed attempts. Try again in {mins} minutes.")
    user = User.from_mongo(await db.users.find_one({"email": email}))
    portal_ok = user and ((user.role != "candidate") if staff else (user.role == "candidate"))
    if not portal_ok or not verify_password(body.password, user.password_hash):
        doc = await db.login_attempts.find_one_and_update(
            {"identifier": ident}, {"$inc": {"count": 1}, "$set": {"last_at": now_utc()}}, upsert=True,
            return_document=ReturnDocument.AFTER)
        if doc["count"] >= MAX_LOGIN_FAILS:
            await db.login_attempts.update_one({"identifier": ident}, {"$set": {
                "locked_until": now_utc() + timedelta(minutes=LOCK_MINUTES), "count": 0}})
        await audit(request, None, "auth.login_failed", "user", user.id if user else None, outcome="failure",
                    actor_email=email, after={"portal": "staff" if staff else "candidate"})
        raise err(401, "invalid_credentials", "Incorrect email or password")
    if user.status != "active":
        raise err(403, "account_inactive", "This account is disabled. Contact the admissions office.")
    await db.login_attempts.delete_many({"identifier": ident})
    if staff and user.role in PRIVILEGED_STAFF:
        out = await issue_challenge("email", user.email, "staff_login", client_ip(request))
        await audit(request, user, "auth.staff_step_up_sent", "otp_challenge", out.get("id"))
        step = {"step_up_required": True, "challenge_id": out["id"], "masked_destination": out.get("masked_destination")}
        if out.get("debug_code"):
            step["debug_code"] = out["debug_code"]
        return step
    token = await open_session(user, request, response)
    await audit(request, user, "auth.login", "user", user.id, after={"portal": "staff" if staff else "candidate"})
    return {"user": user.public(), "access_token": token}


@router.post("/staff/login")
async def staff_login(body: LoginIn, request: Request, response: Response):
    return await _password_login(body, request, response, staff=True)


@router.post("/staff/login/complete")
async def staff_login_complete(body: StaffStepUpIn, request: Request, response: Response):
    ch = await consume_challenge(body.challenge_id, body.code, purpose="staff_login")
    user = User.from_mongo(await db.users.find_one({"email": ch.destination, "role": {"$in": list(PRIVILEGED_STAFF)}}))
    if not user or user.status != "active":
        raise err(401, "invalid_credentials", "Unable to sign in with this code")
    token = await open_session(user, request, response)
    await audit(request, user, "auth.login", "user", user.id, after={"portal": "staff", "method": "email_step_up"})
    return {"user": user.public(), "access_token": token}


@router.post("/candidate/login")
async def candidate_login(body: LoginIn, request: Request, response: Response):
    return await _password_login(body, request, response, staff=False)


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return user.public()


@router.post("/heartbeat")
async def heartbeat(user: User = Depends(current_user)):
    return {"ok": True, "idle_minutes": user.public()["idle_minutes"]}


@router.post("/logout")
async def logout(request: Request, response: Response, user: User = Depends(current_user)):
    await revoke_sessions(user.id, request.state.sid)
    response.delete_cookie(COOKIE, path="/")
    await audit(request, user, "auth.logout", "user", user.id)
    return {"ok": True}


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, request: Request, user: User = Depends(current_user)):
    if not verify_password(body.current_password, user.password_hash):
        raise err(400, "invalid_password", "Current password is incorrect")
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {
        "password_hash": hash_password(body.new_password), "must_change_password": False}})
    await audit(request, user, "auth.password_changed", "user", user.id)
    return {"ok": True}


async def _send_safe(channel: str, dest: str, purpose: str, ip: str) -> dict:
    try:
        return await issue_challenge(channel, dest, purpose, ip)
    except Exception as e:
        detail = getattr(e, "detail", None)
        return {"error": detail if isinstance(detail, dict) else {"code": "send_failed", "message": str(e)}}


@router.post("/candidate/register")
async def register(body: RegisterIn, request: Request, response: Response):
    email = str(body.email).lower()
    if await db.users.find_one({"email": email}):
        raise err(409, "email_exists", "An account with this email exists. Sign in to continue.")
    if await db.users.find_one({"mobile": body.mobile, "role": "candidate"}):
        raise err(409, "mobile_exists", "This mobile number is already registered.")
    user = User(id=str(ObjectId()), email=email, name=body.name.strip(), role="candidate", mobile=body.mobile,
                state=body.state.strip(), city=body.city.strip(), password_hash=hash_password(body.password),
                identity_status="registered", candidate_ref=await _next_candidate_ref())
    try:
        await db.users.insert_one(user.to_mongo())
    except DuplicateKeyError:
        raise err(409, "email_exists", "An account with this email or mobile exists.")
    token = await open_session(user, request, response)
    await audit(request, user, "candidate.registered", "user", user.id,
                after={"email": email, "mobile": _mask("whatsapp", body.mobile), "state": user.state, "city": user.city})
    ip = client_ip(request)
    challenges = {"email": await _send_safe("email", email, "registration", ip),
                  "whatsapp": await _send_safe("whatsapp", body.mobile, "registration", ip)}
    return {"user": user.public(), "access_token": token, "challenges": challenges}


@router.post("/candidate/verification/send")
async def resend_verification(body: ChannelIn, request: Request, user: User = Depends(require_candidate)):
    dest = user.email if body.channel == "email" else user.mobile
    return await issue_challenge(body.channel, dest, "registration", client_ip(request))


@router.post("/candidate/verification/verify")
async def verify_channel(body: VerifyChannelIn, request: Request, user: User = Depends(require_candidate)):
    dest = user.email if body.channel == "email" else user.mobile
    await consume_challenge(body.challenge_id, body.code, purpose="registration", destination=dest)
    field = "email_verified_at" if body.channel == "email" else "whatsapp_verified_at"
    before = {"identity_status": user.identity_status}
    setattr(user, field, now_utc())
    status = "verified" if user.email_verified_at and user.whatsapp_verified_at else "partially_verified"
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {field: getattr(user, field), "identity_status": status}})
    user.identity_status = status
    await audit(request, user, "candidate.channel_verified", "user", user.id, before=before,
                after={"identity_status": status, "channel": body.channel})
    return {"user": user.public()}


async def _start_email_otp(email: str, purpose: str, request: Request) -> dict:
    user = await db.users.find_one({"email": email.lower(), "role": "candidate"})
    if user and (purpose == "recovery" or user.get("email_verified_at")):
        out = await issue_challenge("email", email.lower(), purpose, client_ip(request))
        return {k: out.get(k) for k in ("id", "masked_destination", "expires_at", "resend_available_at",
                                         "attempts_left", "max_attempts", "debug_code") if out.get(k) is not None}
    now = now_utc()
    return {"id": str(ObjectId()), "masked_destination": _mask("email", email.lower()),
            "expires_at": now + timedelta(minutes=OTP_TTL_MIN), "resend_available_at": now + timedelta(seconds=60),
            "attempts_left": 5, "max_attempts": 5}


@router.post("/candidate/otp-login/start")
async def otp_login_start(body: EmailIn, request: Request):
    return await _start_email_otp(str(body.email), "login", request)


@router.post("/candidate/otp-login/complete")
async def otp_login_complete(body: OtpCompleteIn, request: Request, response: Response):
    ch = await consume_challenge(body.challenge_id, body.code, purpose="login")
    user = User.from_mongo(await db.users.find_one({"email": ch.destination, "role": "candidate"}))
    if not user or user.status != "active":
        raise err(401, "invalid_credentials", "Unable to sign in with this code")
    token = await open_session(user, request, response)
    await audit(request, user, "auth.login", "user", user.id, after={"portal": "candidate", "method": "email_otp"})
    return {"user": user.public(), "access_token": token}


@router.post("/candidate/recovery/start")
async def recovery_start(body: EmailIn, request: Request):
    return await _start_email_otp(str(body.email), "recovery", request)


@router.post("/candidate/recovery/complete")
async def recovery_complete(body: RecoveryCompleteIn, request: Request):
    ch = await consume_challenge(body.challenge_id, body.code, purpose="recovery")
    user = User.from_mongo(await db.users.find_one({"email": ch.destination, "role": "candidate"}))
    if not user:
        raise err(400, "invalid_challenge", "Unable to reset password")
    await db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {"password_hash": hash_password(body.new_password)}})
    await revoke_sessions(user.id)
    await audit(request, user, "auth.password_reset", "user", user.id, after={"method": "email_otp"})
    return {"ok": True}
