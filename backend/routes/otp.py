import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Literal, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, TypeAdapter
from pymongo import ReturnDocument

from core import BaseDocument, client_ip, db, log_event, now_utc, rate_limited
from services import email_service, whatsapp_service
from services.email_service import EmailDeliveryError, otp_email, send_email

router = APIRouter(prefix="/api/otp", tags=["otp"])

OTP_TTL_MIN = 10
RESEND_COOLDOWN_S = 60
MAX_ATTEMPTS = 5
MAX_SENDS_PER_DEST_HOUR = 5
MAX_SENDS_PER_IP_HOUR = 30
EMAIL_TEST_SINK = "delivered@resend.dev"
EMAIL_TEST_SINK_DOMAIN = "@resend.dev"
PEPPER = os.environ["OTP_PEPPER"].encode()
E164 = re.compile(r"^\+[1-9]\d{7,14}$")

Channel = Literal["email", "whatsapp"]
Purpose = Literal["registration", "login", "recovery", "step_up_refund", "staff_login"]


class OtpChallenge(BaseDocument):
    channel: Channel
    purpose: Purpose
    destination: str
    masked_destination: str
    code_hash: str
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = MAX_ATTEMPTS
    expires_at: datetime
    resend_available_at: datetime
    created_at: datetime
    verified_at: Optional[datetime] = None
    delivery_provider: str
    delivery_status: str = "queued"
    delivery_ref: Optional[str] = None
    delivery_error: Optional[str] = None
    request_ip: Optional[str] = None
    mocked: bool = False


class SendOtpIn(BaseModel):
    channel: Channel
    destination: str
    purpose: Purpose = "registration"


class VerifyOtpIn(BaseModel):
    challenge_id: str
    code: str


def _hash(cid: str, code: str) -> str:
    return hmac.new(PEPPER, f"{cid}:{code}".encode(), hashlib.sha256).hexdigest()


def _mask(channel: str, dest: str) -> str:
    if channel == "email":
        user, _, dom = dest.partition("@")
        return f"{user[:2]}{'*' * max(len(user) - 2, 1)}@{dom}"
    return f"{dest[:3]}{'*' * (len(dest) - 7)}{dest[-4:]}"


def _public(ch: OtpChallenge) -> dict:
    d = ch.model_dump(exclude={"code_hash", "destination", "request_ip"})
    d["attempts_left"] = max(ch.max_attempts - ch.attempts, 0)
    return d


def _normalize(channel: str, dest: str) -> str:
    dest = dest.strip()
    if channel == "email":
        try:
            return str(TypeAdapter(EmailStr).validate_python(dest)).lower()
        except Exception:
            raise HTTPException(422, {"code": "invalid_destination", "message": "Enter a valid email address"})
    dest = re.sub(r"[\s\-()]", "", dest)
    if not E164.match(dest):
        raise HTTPException(422, {"code": "invalid_destination",
                                  "message": "Enter mobile in international format, e.g. +919876543210"})
    return dest


def _oid(cid: str) -> ObjectId:
    try:
        return ObjectId(cid)
    except (InvalidId, TypeError):
        raise HTTPException(404, {"code": "not_found", "message": "Challenge not found"})


@router.post("/send")
async def send_otp(body: SendOtpIn, request: Request):
    return await issue_challenge(body.channel, body.destination, body.purpose, client_ip(request))


async def issue_challenge(channel: str, destination: str, purpose: str, ip: str) -> dict:
    body = SendOtpIn(channel=channel, destination=destination, purpose=purpose)
    dest = _normalize(body.channel, body.destination)
    if body.channel == "whatsapp" and not whatsapp_service.is_configured():
        raise HTTPException(503, {"code": "whatsapp_not_configured",
                                  "message": "WhatsApp provider is not configured",
                                  "missing": whatsapp_service.missing_vars()})
    now = now_utc()
    scope = {"destination": dest, "channel": body.channel, "purpose": body.purpose}
    latest = await db.otp_challenges.find_one({**scope, "status": "pending"}, sort=[("created_at", -1)])
    if latest and latest["resend_available_at"] > now:
        wait = int((latest["resend_available_at"] - now).total_seconds()) + 1
        raise HTTPException(429, {"code": "resend_cooldown", "message": f"Please wait {wait}s before resending",
                                  "retry_after_seconds": wait})
    dest_cap = 40 if body.purpose == "staff_login" else MAX_SENDS_PER_DEST_HOUR
    ip_cap = 80 if body.purpose == "staff_login" else MAX_SENDS_PER_IP_HOUR
    if await rate_limited(f"otp:{body.purpose}:{body.channel}:{dest}", dest_cap, 3600) or \
            await rate_limited(f"otp-ip:{body.purpose}:{ip}", ip_cap, 3600):
        raise HTTPException(429, {"code": "rate_limited", "message": "Too many OTP requests. Try again later."})

    await db.otp_challenges.update_many({**scope, "status": "pending"}, {"$set": {"status": "superseded"}})
    oid = ObjectId()
    code = f"{secrets.randbelow(10 ** 6):06d}"
    ch = OtpChallenge(
        id=str(oid), channel=body.channel, purpose=body.purpose, destination=dest,
        masked_destination=_mask(body.channel, dest), code_hash=_hash(str(oid), code),
        expires_at=now + timedelta(minutes=OTP_TTL_MIN),
        resend_available_at=now + timedelta(seconds=RESEND_COOLDOWN_S), created_at=now,
        delivery_provider="resend" if body.channel == "email" else "twilio_whatsapp", request_ip=ip,
    )
    await db.otp_challenges.insert_one(ch.to_mongo())

    try:
        if body.channel == "email":
            subject, html = otp_email(code, body.purpose, OTP_TTL_MIN)
            ref, status = await send_email(to=dest, subject=subject, html=html), "sent"
        else:
            ref, status = await whatsapp_service.send_whatsapp_otp(dest, code, OTP_TTL_MIN)
    except (EmailDeliveryError, whatsapp_service.WhatsAppDeliveryError) as e:
        await db.otp_challenges.update_one({"_id": oid}, {"$set": {
            "status": "delivery_failed", "delivery_status": "failed", "delivery_error": str(e),
            "resend_available_at": now}})
        await log_event(body.channel, "otp.delivery_failed", f"OTP delivery failed to {ch.masked_destination}: {e}", "error")
        raise HTTPException(424, {"code": "delivery_failed", "message": str(e), "challenge_id": str(oid)})

    mocked = status == "mocked"
    await db.otp_challenges.update_one({"_id": oid}, {"$set": {"delivery_status": status, "delivery_ref": ref,
                                                               "mocked": mocked}})
    ch.delivery_status, ch.delivery_ref = status, ref
    if mocked:
        await log_event(body.channel, "otp.mocked", f"MOCKED WhatsApp OTP for {ch.masked_destination} "
                        "(no TWILIO_WHATSAPP_CONTENT_SID; not delivered)", "warning", {"challenge_id": str(oid)})
    else:
        await log_event(body.channel, "otp.sent", f"OTP sent to {ch.masked_destination} ({body.purpose})",
                        meta={"challenge_id": str(oid), "provider_ref": ref})
    out = {**_public(ch), "mocked": mocked}
    if dest.endswith(EMAIL_TEST_SINK_DOMAIN) or mocked or email_service.CONSOLE_MODE:
        out["debug_code"] = code
    return out


@router.post("/verify")
async def verify_otp(body: VerifyOtpIn):
    ch = await consume_challenge(body.challenge_id, body.code)
    return {"verified": True, "challenge": _public(ch)}


async def consume_challenge(challenge_id: str, code: str, purpose: Optional[str] = None,
                            destination: Optional[str] = None) -> OtpChallenge:
    oid = _oid(challenge_id)
    ch = OtpChallenge.from_mongo(await db.otp_challenges.find_one({"_id": oid}))
    if not ch:
        raise HTTPException(404, {"code": "not_found", "message": "Code not found or expired. Request a new one."})
    if (purpose and ch.purpose != purpose) or (destination and ch.destination != destination):
        raise HTTPException(400, {"code": "challenge_mismatch", "message": "This code is not valid for this request"})
    errors = {
        "verified": (409, "already_used", "This code has already been used"),
        "superseded": (410, "superseded", "A newer code was sent. Use the latest code."),
        "delivery_failed": (409, "delivery_failed", "Code was not delivered. Request a new one."),
        "locked": (423, "locked", "Too many wrong attempts. Request a new code."),
        "expired": (410, "expired", "Code expired. Request a new one."),
    }
    if ch.status in errors:
        s, c, m = errors[ch.status]
        raise HTTPException(s, {"code": c, "message": m})
    if now_utc() > ch.expires_at:
        await db.otp_challenges.update_one({"_id": oid, "status": "pending"}, {"$set": {"status": "expired"}})
        await log_event(ch.channel, "otp.expired", f"Expired code used for {ch.masked_destination}", "warning")
        raise HTTPException(410, {"code": "expired", "message": "Code expired. Request a new one."})

    doc = await db.otp_challenges.find_one_and_update(
        {"_id": oid, "status": "pending", "attempts": {"$lt": ch.max_attempts}},
        {"$inc": {"attempts": 1}}, return_document=ReturnDocument.AFTER)
    if not doc:
        raise HTTPException(423, {"code": "locked", "message": "Too many wrong attempts. Request a new code."})
    ch = OtpChallenge.from_mongo(doc)

    if hmac.compare_digest(ch.code_hash, _hash(str(oid), code.strip())):
        res = await db.otp_challenges.update_one({"_id": oid, "status": "pending"},
                                                 {"$set": {"status": "verified", "verified_at": now_utc()}})
        if not res.modified_count:
            raise HTTPException(409, {"code": "already_used", "message": "This code has already been used"})
        await log_event(ch.channel, "otp.verified", f"{ch.channel} verified for {ch.masked_destination}", "success")
        return OtpChallenge.from_mongo(await db.otp_challenges.find_one({"_id": oid}))

    left = ch.max_attempts - ch.attempts
    if left <= 0:
        await db.otp_challenges.update_one({"_id": oid, "status": "pending"}, {"$set": {"status": "locked"}})
        await log_event(ch.channel, "otp.locked", f"Challenge locked for {ch.masked_destination}", "error")
        raise HTTPException(423, {"code": "locked", "message": "Too many wrong attempts. Request a new code."})
    await log_event(ch.channel, "otp.invalid", f"Wrong code for {ch.masked_destination} ({left} left)", "warning")
    raise HTTPException(400, {"code": "invalid_code", "message": f"Incorrect code. {left} attempts left.",
                              "attempts_left": left})


@router.get("/challenges/{challenge_id}")
async def get_challenge(challenge_id: str):
    oid = _oid(challenge_id)
    ch = OtpChallenge.from_mongo(await db.otp_challenges.find_one({"_id": oid}))
    if not ch:
        raise HTTPException(404, {"code": "not_found", "message": "Challenge not found"})
    if ch.channel == "whatsapp" and ch.delivery_ref and not ch.delivery_ref.startswith("wa_mock_") \
            and whatsapp_service.is_configured():
        try:
            status, err = await whatsapp_service.fetch_status(ch.delivery_ref)
            await db.otp_challenges.update_one({"_id": oid}, {"$set": {"delivery_status": status, "delivery_error": err}})
            ch.delivery_status, ch.delivery_error = status, err
        except Exception:
            pass
    return _public(ch)
