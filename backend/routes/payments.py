import asyncio
import hashlib
import json
import logging
import os
import secrets
from datetime import datetime
from typing import Optional

import stripe
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core import BaseDocument, IST, db, inr, log_event, now_utc
from routes.otp import consume_challenge
from routes.policies import active_policy
from security import User, audit, err, require
from services import stripe_gateway as gw
from services.notify import notify

logger = logging.getLogger(__name__)
router = APIRouter(tags=["payments"])


def fee_catalog() -> dict:
    fee = int(round(float(os.environ["APPLICATION_FEE_INR"]) * 100))
    return {"application_fee": {"code": "application_fee", "description": "WeSchool Application Fee (Admissions 2027)",
                                "amount_paise": fee}}


class PaymentOrder(BaseDocument):
    order_ref: str
    fee_code: str
    description: str
    amount_paise: int
    currency: str = "INR"
    candidate_name: str
    candidate_email: str
    candidate_id: Optional[str] = None
    application_ref: Optional[str] = None
    provider: str = "stripe"
    provider_session_id: Optional[str] = None
    provider_payment_intent: Optional[str] = None
    checkout_url: Optional[str] = None
    status: str = "created"
    refunded_paise: int = 0
    refund_reserved_paise: int = 0
    idempotency_key: str
    payload_hash: str
    verified_via: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    paid_at: Optional[datetime] = None
    origin: str = "gateway"
    allotment_id: Optional[str] = None
    offline_mode: Optional[str] = None
    txn_ref: Optional[str] = None
    txn_date: Optional[str] = None
    proof_file_id: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class Refund(BaseDocument):
    refund_ref: str
    order_id: str
    amount_paise: int
    reason: str
    status: str = "pending_provider"
    provider_refund_id: Optional[str] = None
    provider_status: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    mocked: bool = False
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class CreateOrderIn(BaseModel):
    fee_code: str
    candidate_name: str = Field(min_length=2, max_length=120)
    candidate_email: EmailStr
    application_ref: Optional[str] = None
    origin_url: str
    idempotency_key: str = Field(min_length=8, max_length=100)


class RefundIn(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    reason: str = Field(min_length=3, max_length=300)
    idempotency_key: str = Field(min_length=8, max_length=100)
    otp_challenge_id: str = Field(min_length=1)
    otp_code: str = Field(min_length=6, max_length=6)


REFUNDABLE = ("paid", "duplicate_payment")


def _ref(prefix: str) -> str:
    return f"{prefix}-{now_utc().astimezone(IST):%Y%m%d}-{secrets.token_hex(3).upper()}"


def _oid(v: str) -> ObjectId:
    try:
        return ObjectId(v)
    except (InvalidId, TypeError):
        raise HTTPException(404, {"code": "not_found", "message": "Not found"})


def _order_out(o: PaymentOrder, refunds: list[Refund]) -> dict:
    d = o.model_dump(exclude={"payload_hash"})
    d["amount"] = o.amount_paise / 100
    d["refunded_amount"] = o.refunded_paise / 100
    d["refundable_amount"] = (o.amount_paise - o.refund_reserved_paise) / 100 if o.status in REFUNDABLE else 0
    d["refund_state"] = "none" if not o.refunded_paise else ("full" if o.refunded_paise >= o.amount_paise else "partial")
    d["refunds"] = [{**r.model_dump(), "amount": r.amount_paise / 100} for r in refunds]
    return d


async def _load_order(oid: ObjectId) -> PaymentOrder:
    o = PaymentOrder.from_mongo(await db.payment_orders.find_one({"_id": oid}))
    if not o:
        raise HTTPException(404, {"code": "not_found", "message": "Order not found"})
    return o


async def _refunds_for(order_id: str) -> list[Refund]:
    return [Refund.from_mongo(r) async for r in db.refunds.find({"order_id": order_id}).sort("created_at", 1)]


def _webhook_url(request: Request) -> str:
    base = str(request.base_url)
    if request.headers.get("x-forwarded-proto") == "https" and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return f"{base}api/webhook/stripe"


async def apply_session(order: PaymentOrder, session, via: str) -> bool:
    oid = ObjectId(order.id)
    now = now_utc()
    if session.payment_status == "paid":
        if session.amount_total != order.amount_paise or (session.currency or "").lower() != "inr":
            await db.payment_orders.update_one({"_id": oid, "status": {"$ne": "paid"}}, {"$set": {
                "status": "amount_mismatch", "failure_reason": f"Provider reported {session.amount_total} {session.currency}",
                "updated_at": now}})
            await log_event("stripe", "payment.mismatch", f"{order.order_ref}: amount/currency mismatch", "error")
            return False
        try:
            res = await db.payment_orders.update_one(
                {"_id": oid, "status": {"$in": ["created", "pending", "expired", "failed"]}},
                {"$set": {"status": "paid", "paid_at": now, "provider_payment_intent": session.payment_intent,
                          "verified_via": via, "updated_at": now}})
        except DuplicateKeyError:
            res = await db.payment_orders.update_one(
                {"_id": oid, "status": {"$in": ["created", "pending", "expired", "failed"]}},
                {"$set": {"status": "duplicate_payment", "paid_at": now, "provider_payment_intent": session.payment_intent,
                          "verified_via": via, "failure_reason": "Another payment for this fee is already recorded",
                          "updated_at": now}})
            if res.modified_count:
                await log_event("stripe", "payment.duplicate", f"{order.order_ref}: duplicate payment flagged for refund", "error")
            return False
        if res.modified_count:
            await log_event("stripe", "payment.verified", f"{order.order_ref} paid {inr(order.amount_paise)} (via {via})",
                            "success", {"order_id": order.id})
            return True
    elif session.status == "expired":
        res = await db.payment_orders.update_one({"_id": oid, "status": {"$in": ["created", "pending"]}},
                                                 {"$set": {"status": "expired", "updated_at": now}})
        if res.modified_count:
            await log_event("stripe", "payment.expired", f"{order.order_ref} checkout expired", "warning")
    return False


async def _refresh_one(order: PaymentOrder) -> None:
    """Confirm one open checkout without letting a slow or dead session hold the page."""
    if not order.provider_session_id:
        return
    try:
        session = await asyncio.wait_for(gw.retrieve_session(order.provider_session_id), timeout=2.5)
    except stripe.error.InvalidRequestError as e:
        if getattr(e, "code", None) == "resource_missing" or "No such" in str(e):
            await db.payment_orders.update_one(
                {"_id": ObjectId(order.id), "status": {"$in": ["created", "pending"]}},
                {"$set": {"status": "expired", "failure_reason": "Checkout session is no longer available",
                          "updated_at": now_utc()}})
        return
    except Exception:
        return
    try:
        await apply_session(order, session, "status_poll")
    except Exception:
        return


async def refresh_open_checkouts(candidate_id: str, fee_code: Optional[str] = None) -> None:
    q = {"candidate_id": candidate_id, "status": {"$in": ["created", "pending"]}, "provider_session_id": {"$type": "string"}}
    if fee_code:
        q["fee_code"] = fee_code
    orders = [PaymentOrder.from_mongo(d) async for d in db.payment_orders.find(q).limit(8)]
    if orders:
        await asyncio.gather(*(_refresh_one(o) for o in orders))


async def _settle_refund(r: Refund, provider_status: str, provider_id: Optional[str] = None, error: Optional[str] = None):
    rid, now = ObjectId(r.id), now_utc()
    base = {"provider_status": provider_status, "updated_at": now}
    if provider_id:
        base["provider_refund_id"] = provider_id
    if provider_status == "succeeded":
        res = await db.refunds.update_one({"_id": rid, "status": "pending_provider"},
                                          {"$set": {**base, "status": "succeeded", "error": None}})
        if res.modified_count:
            await db.payment_orders.update_one({"_id": ObjectId(r.order_id)}, {"$inc": {"refunded_paise": r.amount_paise}})
            await log_event("stripe", "refund.succeeded", f"{r.refund_ref} refunded {inr(r.amount_paise)}", "success")
    elif provider_status in ("failed", "canceled", "error"):
        res = await db.refunds.update_one({"_id": rid, "status": "pending_provider"},
                                          {"$set": {**base, "status": "failed", "error": error}})
        if res.modified_count:
            await db.payment_orders.update_one({"_id": ObjectId(r.order_id)},
                                               {"$inc": {"refund_reserved_paise": -r.amount_paise}})
            await log_event("stripe", "refund.failed", f"{r.refund_ref} failed: {error or provider_status}", "error")
    else:
        await db.refunds.update_one({"_id": rid}, {"$set": base})


async def _dispatch_refund(r: Refund, order: PaymentOrder):
    await db.refunds.update_one({"_id": ObjectId(r.id)}, {"$inc": {"attempts": 1}})
    pi = order.provider_payment_intent
    if not pi and order.provider_session_id:
        try:
            pi = (await gw.retrieve_session(order.provider_session_id)).payment_intent
        except stripe.error.StripeError:
            pi = None
    if not pi and not r.mocked:
        return await _settle_refund(r, "error", error="Payment intent unavailable for this order")
    try:
        pr = await gw.create_refund(payment_intent=pi, amount_paise=r.amount_paise, refund_id=r.id, order_id=r.order_id)
    except stripe.error.StripeError as e:
        return await _settle_refund(r, "error", error=(e.user_message or str(e))[:300])
    if r.mocked:
        await log_event("stripe", "refund.mocked", f"{r.refund_ref}: MOCKED provider refund {pr.id}", "warning")
    await _settle_refund(r, pr.status, provider_id=pr.id, error=getattr(pr, "failure_reason", None))


@router.get("/api/payments/config")
async def payments_config():
    return {**gw.mode(), "currency": "INR",
            "fees": [{**f, "amount": f["amount_paise"] / 100} for f in fee_catalog().values()]}


@router.post("/api/payments/orders", dependencies=[Depends(require("payments.read"))])
async def create_order(body: CreateOrderIn, request: Request):
    fee = fee_catalog().get(body.fee_code)
    if not fee:
        raise HTTPException(422, {"code": "unknown_fee", "message": "Unknown fee code"})
    return await open_checkout(fee_code=body.fee_code, description=fee["description"], amount_paise=fee["amount_paise"],
                               name=body.candidate_name, email=str(body.candidate_email),
                               application_ref=body.application_ref, idempotency_key=body.idempotency_key,
                               origin=body.origin_url, request=request)


async def open_checkout(*, fee_code: str, description: str, amount_paise: int, name: str, email: str,
                        application_ref: Optional[str], idempotency_key: str, origin: str, request: Request,
                        candidate_id: Optional[str] = None, return_base: str = "/payment") -> dict:
    payload_hash = hashlib.sha256(json.dumps(
        [fee_code, name.strip(), email.lower(), application_ref or "", amount_paise]).encode()).hexdigest()
    existing = PaymentOrder.from_mongo(await db.payment_orders.find_one({"idempotency_key": idempotency_key}))
    if existing:
        if existing.payload_hash != payload_hash:
            raise HTTPException(409, {"code": "idempotency_conflict",
                                      "message": "Idempotency key reused with a different payload"})
        return {**_order_out(existing, await _refunds_for(existing.id)), "idempotent_replay": True}

    now = now_utc()
    order = PaymentOrder(id=str(ObjectId()), order_ref=_ref("WS-PAY"), fee_code=fee_code,
                         description=description, amount_paise=amount_paise,
                         candidate_name=name.strip(), candidate_email=email.lower(), candidate_id=candidate_id,
                         application_ref=application_ref, idempotency_key=idempotency_key,
                         payload_hash=payload_hash, created_at=now, updated_at=now)
    try:
        await db.payment_orders.insert_one(order.to_mongo())
    except DuplicateKeyError:
        dup = PaymentOrder.from_mongo(await db.payment_orders.find_one({"idempotency_key": idempotency_key}))
        return {**_order_out(dup, []), "idempotent_replay": True}

    origin = origin.rstrip("/")
    try:
        session = await gw.create_checkout(
            order_id=order.id, order_ref=order.order_ref, description=order.description,
            amount_paise=order.amount_paise, email=order.candidate_email,
            success_url=f"{origin}{return_base}/success?session_id={{CHECKOUT_SESSION_ID}}&order_id={order.id}",
            cancel_url=f"{origin}{return_base}/cancel?order_id={order.id}", webhook_url=_webhook_url(request))
    except stripe.error.StripeError as e:
        await db.payment_orders.update_one({"_id": ObjectId(order.id)}, {"$set": {
            "status": "failed", "failure_reason": (e.user_message or str(e))[:300], "updated_at": now_utc()}})
        await log_event("stripe", "checkout.failed", f"{order.order_ref}: checkout creation failed", "error")
        raise HTTPException(424, {"code": "gateway_error", "message": "Could not create checkout session"})

    await db.payment_orders.update_one({"_id": ObjectId(order.id)}, {"$set": {
        "provider_session_id": session.id, "checkout_url": session.url, "status": "pending", "updated_at": now_utc()}})
    await log_event("stripe", "checkout.created", f"{order.order_ref}: checkout created for {inr(order.amount_paise)}",
                    meta={"order_id": order.id, "session_id": session.id})
    return _order_out(await _load_order(ObjectId(order.id)), [])


@router.get("/api/payments/orders", dependencies=[Depends(require("payments.read"))])
async def list_orders():
    orders = [PaymentOrder.from_mongo(d) async for d in db.payment_orders.find().sort("created_at", -1).limit(50)]
    grouped: dict[str, list[Refund]] = {}
    if orders:
        async for raw in db.refunds.find({"order_id": {"$in": [o.id for o in orders]}}).sort("created_at", 1):
            grouped.setdefault(raw["order_id"], []).append(Refund.from_mongo(raw))
    return [_order_out(o, grouped.get(o.id, [])) for o in orders]


@router.get("/api/payments/orders/{order_id}", dependencies=[Depends(require("payments.read"))])
async def get_order(order_id: str):
    oid = _oid(order_id)
    order = await _load_order(oid)
    if order.status in ("created", "pending") and order.provider_session_id:
        await _refresh_one(order)
        order = await _load_order(oid)
    refunds = await _refunds_for(order.id)
    for r in refunds:
        if r.status == "pending_provider" and r.provider_refund_id:
            try:
                pr = await gw.retrieve_refund(r.provider_refund_id)
                await _settle_refund(r, pr.status, error=getattr(pr, "failure_reason", None))
            except stripe.error.StripeError:
                pass
    return _order_out(await _load_order(oid), await _refunds_for(order.id))


async def signoff_threshold_paise() -> int:
    try:
        _, pol = await active_policy("refund_policy")
    except HTTPException:
        return 5_000_000
    return int(round(float(pol.get("super_admin_signoff_above_inr", 50000)) * 100))


async def open_signoff(*, order_id: str, order_ref: str, amount_paise: int, reason: str, requested_by: str,
                       cancellation_id: Optional[str] = None) -> dict:
    existing = await db.refund_signoffs.find_one({"order_id": order_id, "amount_paise": amount_paise, "status": "pending"})
    if existing:
        return existing
    doc = {"order_id": order_id, "order_ref": order_ref, "amount_paise": amount_paise, "reason": reason,
           "requested_by": requested_by, "status": "pending", "cancellation_id": cancellation_id,
           "created_at": now_utc(), "used_at": None}
    doc["_id"] = (await db.refund_signoffs.insert_one(doc)).inserted_id
    return doc


def _signoff_out(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "_id"} | {"id": str(d["_id"]), "amount": d["amount_paise"] / 100}


async def _tell_accounts(title: str, body: str) -> None:
    async for u in db.users.find({"role": "accounts_operator"}, {"_id": 1}):
        await notify(str(u["_id"]), "refund", title, body, email=True)


class SignoffDecision(BaseModel):
    remarks: str = Field(default="", max_length=300)


@router.get("/api/refund-signoffs")
async def list_signoffs(status: Optional[str] = "pending", _: User = Depends(require("refunds.signoff"))):
    q = {"status": status} if status else {}
    return [_signoff_out(d) async for d in db.refund_signoffs.find(q).sort("created_at", 1)]


@router.post("/api/refund-signoffs/{sid}/approve")
async def approve_signoff(sid: str, body: SignoffDecision, request: Request, user: User = Depends(require("refunds.signoff"))):
    return await _decide_signoff(sid, "approved", body.remarks, request, user)


@router.post("/api/refund-signoffs/{sid}/reject")
async def reject_signoff(sid: str, body: SignoffDecision, request: Request, user: User = Depends(require("refunds.signoff"))):
    if len(body.remarks.strip()) < 5:
        raise err(422, "remarks_required", "Say why this refund will not be paid out")
    return await _decide_signoff(sid, "rejected", body.remarks, request, user)


async def _decide_signoff(sid: str, status: str, remarks: str, request: Request, user: User) -> dict:
    oid = _oid(sid)
    now = now_utc()
    doc = await db.refund_signoffs.find_one_and_update(
        {"_id": oid, "status": "pending"},
        {"$set": {"status": status, "decided_by": user.email, "decided_at": now, "remarks": remarks.strip()}},
        return_document=ReturnDocument.AFTER)
    if not doc:
        current = await db.refund_signoffs.find_one({"_id": oid})
        raise err(409, "invalid_state", f"Sign-off is {current['status'] if current else 'missing'}")
    cid = doc.get("cancellation_id")
    if cid and ObjectId.is_valid(cid):
        if status == "approved":
            await db.cancellations.update_one({"_id": ObjectId(cid), "status": "pending_signoff"}, {"$set": {
                "status": "approved", "updated_at": now}, "$push": {"history": {
                    "action": "signoff_approved", "by": user.email, "at": now, "remarks": remarks.strip()}}})
        else:
            await db.cancellations.update_one({"_id": ObjectId(cid), "status": "pending_signoff"}, {"$set": {
                "status": "signoff_rejected", "review_remarks": remarks.strip(), "updated_at": now}, "$push": {"history": {
                    "action": "signoff_rejected", "by": user.email, "at": now, "remarks": remarks.strip()}}})
            c = await db.cancellations.find_one({"_id": ObjectId(cid)})
            if c:
                await notify(c["candidate_id"], "refund", "Refund will not be paid",
                             f"The refund for {c['cancellation_ref']} was declined. {remarks.strip()}", email=True)
    verb = "approved" if status == "approved" else "declined"
    await _tell_accounts(
        f"Refund sign-off {verb}",
        f"{doc['order_ref']}: ₹{doc['amount_paise'] / 100:,.2f} was {verb} by Super Admin."
        + ("" if status == "approved" else " The payout will not proceed."))
    await audit(request, user, f"refund.signoff_{status}", "refund_signoff", sid,
                after={"order_ref": doc["order_ref"], "amount_paise": doc["amount_paise"], "status": status},
                reason=remarks.strip() or None)
    return _signoff_out(doc)


@router.post("/api/payments/orders/{order_id}/refunds")
async def create_refund(order_id: str, body: RefundIn, request: Request,
                        user: User = Depends(require("payments.refund"))):
    return await execute_refund(order_id, body.amount, body.reason, body.idempotency_key, request, user,
                                (body.otp_challenge_id, body.otp_code))


async def execute_refund(order_id: str, amount: Optional[float], reason: str, idempotency_key: str, request: Request,
                         user: User, step_up: tuple[str, str]) -> dict:
    oid = _oid(order_id)
    order = await _load_order(oid)
    prior = Refund.from_mongo(await db.refunds.find_one({"idempotency_key": idempotency_key}))
    if prior:
        if prior.order_id != order.id:
            raise HTTPException(409, {"code": "idempotency_conflict", "message": "Idempotency key used for another order"})
        return {"refund": {**prior.model_dump(), "amount": prior.amount_paise / 100}, "idempotent_replay": True}
    if order.status not in REFUNDABLE:
        raise HTTPException(409, {"code": "not_refundable", "message": "Only verified paid orders can be refunded"})
    remaining = order.amount_paise - order.refund_reserved_paise
    amt = int(round(amount * 100)) if amount else remaining
    if remaining <= 0 or amt <= 0:
        raise HTTPException(422, {"code": "nothing_refundable", "message": "No refundable balance remains"})
    if amt > remaining:
        raise HTTPException(422, {"code": "exceeds_refundable", "message": "Refund exceeds the remaining refundable amount"})
    signoff = None
    if amt >= await signoff_threshold_paise():
        signoff = await db.refund_signoffs.find_one({
            "order_id": order.id, "amount_paise": amt, "status": "approved", "used_at": None})
        if not signoff:
            pending = await db.refund_signoffs.find_one({
                "order_id": order.id, "amount_paise": amt, "status": "pending"})
            if not pending:
                pending = await open_signoff(order_id=order.id, order_ref=order.order_ref, amount_paise=amt,
                                             reason=reason.strip(), requested_by=user.email)
            raise HTTPException(409, {"code": "signoff_required",
                                      "message": "This refund needs Super Admin sign-off before payout.",
                                      "signoff_id": str(pending["_id"])})
    await consume_challenge(step_up[0], step_up[1], purpose="step_up_refund", destination=user.email.lower())
    await audit(request, user, "refund.step_up_verified", "payment_order", order.id)
    if signoff:
        claimed = await db.refund_signoffs.update_one(
            {"_id": signoff["_id"], "status": "approved", "used_at": None},
            {"$set": {"used_at": now_utc(), "used_by": user.email}})
        if not claimed.modified_count:
            raise HTTPException(409, {"code": "signoff_required", "message": "Super Admin sign-off was already used."})
    reserved = await db.payment_orders.find_one_and_update(
        {"_id": oid, "status": {"$in": list(REFUNDABLE)},
         "$expr": {"$lte": [{"$add": ["$refund_reserved_paise", amt]}, "$amount_paise"]}},
        {"$inc": {"refund_reserved_paise": amt}}, return_document=ReturnDocument.AFTER)
    if not reserved:
        if signoff:
            await db.refund_signoffs.update_one({"_id": signoff["_id"]}, {"$set": {"used_at": None, "used_by": None}})
        raise HTTPException(422, {"code": "exceeds_refundable",
                                  "message": "Refund exceeds the remaining refundable amount"})
    now = now_utc()
    r = Refund(id=str(ObjectId()), refund_ref=_ref("WS-RFD"), order_id=order.id, amount_paise=amt,
               reason=reason.strip(), idempotency_key=idempotency_key, mocked=gw.refunds_mocked(),
               created_at=now, updated_at=now)
    try:
        await db.refunds.insert_one(r.to_mongo())
    except DuplicateKeyError:
        await db.payment_orders.update_one({"_id": oid}, {"$inc": {"refund_reserved_paise": -amt}})
        prior = Refund.from_mongo(await db.refunds.find_one({"idempotency_key": idempotency_key}))
        return {"refund": {**prior.model_dump(), "amount": prior.amount_paise / 100}, "idempotent_replay": True}
    if order.provider == "offline":
        r.mocked = True
        await db.refunds.update_one({"_id": ObjectId(r.id)}, {"$set": {"mocked": True}})
    await log_event("stripe", "refund.requested", f"{r.refund_ref}: {inr(amt)} on {order.order_ref}")
    await _dispatch_refund(r, order)
    r = Refund.from_mongo(await db.refunds.find_one({"_id": ObjectId(r.id)}))
    await audit(request, user, "refund.executed", "refund", r.id, after={"order_ref": order.order_ref, "amount_paise": amt,
                "status": r.status, "mocked": r.mocked}, reason=r.reason)
    return {"refund": {**r.model_dump(), "amount": r.amount_paise / 100}, "idempotent_replay": False}


@router.post("/api/payments/refunds/{refund_id}/retry", dependencies=[Depends(require("payments.refund"))])
async def retry_refund(refund_id: str):
    rid = _oid(refund_id)
    r = Refund.from_mongo(await db.refunds.find_one({"_id": rid}))
    if not r:
        raise HTTPException(404, {"code": "not_found", "message": "Refund not found"})
    if r.status != "failed":
        return {"refund": {**r.model_dump(), "amount": r.amount_paise / 100}, "idempotent_replay": True}
    oid = ObjectId(r.order_id)
    reserved = await db.payment_orders.find_one_and_update(
        {"_id": oid, "status": "paid",
         "$expr": {"$lte": [{"$add": ["$refund_reserved_paise", r.amount_paise]}, "$amount_paise"]}},
        {"$inc": {"refund_reserved_paise": r.amount_paise}})
    if not reserved:
        raise HTTPException(422, {"code": "exceeds_refundable", "message": "Refund exceeds the remaining refundable amount"})
    claimed = await db.refunds.update_one({"_id": rid, "status": "failed"},
                                          {"$set": {"status": "pending_provider", "updated_at": now_utc()}})
    if not claimed.modified_count:
        await db.payment_orders.update_one({"_id": oid}, {"$inc": {"refund_reserved_paise": -r.amount_paise}})
    else:
        r.status = "pending_provider"
        await _dispatch_refund(r, await _load_order(oid))
    r = Refund.from_mongo(await db.refunds.find_one({"_id": rid}))
    return {"refund": {**r.model_dump(), "amount": r.amount_paise / 100}, "idempotent_replay": False}


class _EventSession:
    """Gateway fields copied from a verified webhook when the session cannot be retrieved."""

    def __init__(self, obj: dict):
        self.payment_status = obj.get("payment_status")
        self.amount_total = obj.get("amount_total")
        self.currency = obj.get("currency") or "inr"
        self.payment_intent = obj.get("payment_intent")
        self.status = obj.get("status")


async def _order_for_checkout(obj: dict, signature_verified: bool):
    order = PaymentOrder.from_mongo(await db.payment_orders.find_one({"provider_session_id": obj.get("id")}))
    if order or not signature_verified:
        return order
    meta = obj.get("metadata") or {}
    raw = meta.get("order_id") or obj.get("client_reference_id")
    if raw and ObjectId.is_valid(str(raw)):
        return PaymentOrder.from_mongo(await db.payment_orders.find_one({"_id": ObjectId(str(raw))}))
    return None


async def _session_for_event(obj: dict, signature_verified: bool):
    if obj.get("id"):
        try:
            return await gw.retrieve_session(obj["id"])
        except Exception:
            logger.warning("checkout session %s could not be retrieved", obj.get("id"))
    if signature_verified and obj.get("payment_status"):
        return _EventSession(obj)
    return None


async def process_event(event: dict, signature_verified: bool) -> str:
    try:
        await db.payment_events.insert_one({"provider": "stripe", "provider_event_id": event["id"],
                                            "type": event["type"], "signature_verified": signature_verified,
                                            "received_at": now_utc()})
    except DuplicateKeyError:
        await log_event("stripe", "webhook.duplicate", f"Duplicate event {event['id']} ignored", "warning")
        return "duplicate"
    obj, etype = event["data"]["object"], event["type"]
    await log_event("stripe", "webhook.received", f"{etype} ({event['id']})")
    if etype.startswith("checkout.session."):
        order = await _order_for_checkout(obj, signature_verified)
        if order:
            session = await _session_for_event(obj, signature_verified)
            if session:
                await apply_session(order, session, "webhook")
    elif etype.startswith("refund.") or etype == "charge.refunded":
        ids = [obj["id"]] if etype.startswith("refund.") else [x["id"] for x in obj.get("refunds", {}).get("data", [])]
        for pid in ids:
            r = Refund.from_mongo(await db.refunds.find_one({"provider_refund_id": pid}))
            if not r and signature_verified:
                meta = obj.get("metadata") or {}
                if meta.get("refund_id") and ObjectId.is_valid(str(meta["refund_id"])):
                    r = Refund.from_mongo(await db.refunds.find_one({"_id": ObjectId(str(meta["refund_id"]))}))
            if not r:
                continue
            try:
                pr = await gw.retrieve_refund(pid)
                await _settle_refund(r, pr.status, error=getattr(pr, "failure_reason", None))
            except Exception:
                logger.warning("refund %s could not be retrieved", pid)
                if signature_verified and obj.get("status") in ("succeeded", "failed", "pending", "canceled"):
                    await _settle_refund(r, obj["status"], provider_id=pid)
    return "processed"


@router.post("/api/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    if os.environ.get("STRIPE_WEBHOOK_SECRET"):
        try:
            event = gw.construct_event(payload, request.headers.get("stripe-signature", ""))
            event, verified = event.to_dict(), True
        except (stripe.error.SignatureVerificationError, ValueError):
            await log_event("stripe", "webhook.rejected", "Webhook signature invalid", "error")
            raise HTTPException(400, {"code": "invalid_signature", "message": "Invalid signature"})
    else:
        try:
            event, verified = json.loads(payload), False
        except ValueError:
            raise HTTPException(400, {"code": "invalid_payload", "message": "Invalid payload"})
    if not isinstance(event, dict) or "id" not in event or "type" not in event:
        raise HTTPException(400, {"code": "invalid_payload", "message": "Invalid payload"})
    try:
        result = await process_event(event, verified)
    except stripe.error.StripeError:
        logger.exception("webhook processing failed")
        raise HTTPException(424, {"code": "gateway_error", "message": "Could not verify with provider"})
    return {"status": result}


@router.post("/api/poc/payments/{order_id}/replay-callback", dependencies=[Depends(require("payments.refund"))])
async def replay_callback(order_id: str, times: int = 3):
    order = await _load_order(_oid(order_id))
    if not order.provider_session_id:
        raise HTTPException(409, {"code": "no_session", "message": "Order has no checkout session"})
    event = {"id": f"evt_poc_replay_{order.id}", "type": "checkout.session.completed",
             "data": {"object": {"id": order.provider_session_id}}}
    results = [await process_event(event, False) for _ in range(max(1, min(times, 10)))]
    return {"results": results,
            "event_records": await db.payment_events.count_documents({"provider_event_id": event["id"]}),
            "orders_for_session": await db.payment_orders.count_documents({"provider_session_id": order.provider_session_id}),
            "order": _order_out(await _load_order(ObjectId(order.id)), await _refunds_for(order.id))}
