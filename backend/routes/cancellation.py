import re
from datetime import date, datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from core import IST, BaseDocument, db, now_utc
from routes.allotment import Allotment, _hist, release_seat
from routes.application import active_cycle
from routes.payments import _ref, execute_refund, open_signoff, signoff_threshold_paise
from routes.policies import active_policy
from security import User, audit, err, require, require_any, require_candidate
from services import pdf_service
from services.notify import notify
from services.xlsx import xlsx_response

router = APIRouter(prefix="/api", tags=["cancellation"])
IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


class Cancellation(BaseDocument):
    cycle_id: str
    cancellation_ref: str
    candidate_id: str
    application_ref: str
    allotment_id: str
    program_code: str
    reason: str
    bank: dict
    bank_ref: str
    status: str = "requested"
    quote: Optional[dict] = None
    refund_id: Optional[str] = None
    refund_status: Optional[str] = None
    review_remarks: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    seat_released: bool = False
    history: list[dict] = []
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


def refund_balance(*, paid_paise: int, refunded_paise: int, reserved_paise: int,
                   refund_percent: int, processing_fee_paise: int) -> dict:
    """Policy refund still payable after money already sent back on the admission fee.

    The entitlement is calculated on the original fee. Succeeded refunds reduce what
    is still due, and in-flight reservations reduce what the gateway can still accept.
    """
    policy_gross = int(paid_paise) * int(refund_percent) // 100
    fee = int(processing_fee_paise) if policy_gross else 0
    entitlement = max(0, policy_gross - fee)
    already = max(0, int(refunded_paise))
    available = max(0, int(paid_paise) - int(reserved_paise))
    return {
        "paid_paise": int(paid_paise),
        "already_refunded_paise": already,
        "entitlement_paise": entitlement,
        "processing_fee_paise": fee,
        "deduction_paise": max(0, int(paid_paise) - entitlement),
        "refund_paise": min(max(0, entitlement - already), available),
    }


def _available_paise(order: dict) -> int:
    return max(0, int(order["amount_paise"]) - int(order.get("refund_reserved_paise") or 0))


def _order_for_payout(orders: list[dict], payable: int, preferred: Optional[str]) -> Optional[str]:
    if not orders:
        return preferred
    if preferred:
        match = next((o for o in orders if str(o["_id"]) == preferred), None)
        if match and (payable <= 0 or _available_paise(match) >= payable):
            return preferred
    capable = [o for o in orders if _available_paise(o) >= payable]
    pool = capable or orders
    return str(max(pool, key=_available_paise)["_id"])


async def _admission_orders(cid: str) -> list[dict]:
    return [o async for o in db.payment_orders.find({"candidate_id": cid, "fee_code": "admission_fee", "status": "paid"})]


async def quote(cid: str, on: Optional[date] = None) -> dict:
    rv, pol = await active_policy("refund_policy")
    av, rules = await active_policy("admission_rules")
    today = on or datetime.now(IST).date()
    days = (date.fromisoformat(rules["programme_start_date"]) - today).days
    tier = next((t for t in sorted(pol["tiers"], key=lambda t: -t["days_before_start_min"]) if days >= t["days_before_start_min"]), pol["tiers"][-1])
    orders = await _admission_orders(cid)
    paid = sum(int(o["amount_paise"]) for o in orders)
    refunded = sum(int(o.get("refunded_paise") or 0) for o in orders)
    reserved = sum(int(o.get("refund_reserved_paise") or 0) for o in orders)
    balance = refund_balance(paid_paise=paid, refunded_paise=refunded, reserved_paise=reserved,
                             refund_percent=tier["refund_percent"], processing_fee_paise=int(pol["processing_fee_inr"] * 100))
    return {"policy_version": rv, "admission_rules_version": av, "days_before_start": days, "tier": tier["label"],
            "refund_percent": tier["refund_percent"], **balance,
            "order_id": _order_for_payout(orders, balance["refund_paise"], None),
            "computed_on": today.isoformat()}


_QUOTE_MONEY = ("paid_paise", "already_refunded_paise", "entitlement_paise", "processing_fee_paise",
                "deduction_paise", "refund_paise", "order_id")


async def refresh_quote(q: Optional[dict], candidate_id: str, cancellation_id: Optional[str] = None,
                        orders: Optional[list] = None) -> Optional[dict]:
    """Recompute a stored quote from the live admission-fee refunds.

    Quotes are snapshotted at request and approval. A later partial refund on the
    Payments page must shrink the amount still due, or the payout asks the gateway
    for more than the charge has left.
    """
    if not q:
        return q
    if orders is None:
        orders = await _admission_orders(candidate_id)
    percent = int(q.get("refund_percent") or 0)
    proc = int(q.get("processing_fee_paise") or 0)
    if orders:
        paid = sum(int(o["amount_paise"]) for o in orders)
        refunded = sum(int(o.get("refunded_paise") or 0) for o in orders)
        reserved = sum(int(o.get("refund_reserved_paise") or 0) for o in orders)
    else:
        paid = int(q.get("paid_paise") or 0)
        refunded = int(q.get("already_refunded_paise") or 0)
        reserved = refunded
    balance = refund_balance(paid_paise=paid, refunded_paise=refunded, reserved_paise=reserved,
                             refund_percent=percent, processing_fee_paise=proc)
    out = {**q, **balance, "order_id": _order_for_payout(orders, balance["refund_paise"], q.get("order_id"))}
    if cancellation_id and any(out.get(k) != q.get(k) for k in _QUOTE_MONEY):
        await db.cancellations.update_one({"_id": ObjectId(cancellation_id)}, {"$set": {"quote": out}})
        if out.get("order_id") and out["refund_paise"] > 0:
            await db.refund_signoffs.update_many(
                {"cancellation_id": cancellation_id, "status": "pending", "amount_paise": {"$ne": out["refund_paise"]}},
                {"$set": {"amount_paise": out["refund_paise"]}})
    return out


async def _align_approved_signoff(cancellation_id: str, order_id: str, payable: int) -> None:
    """A sign-off for the original quote still covers the smaller remainder."""
    if payable <= 0 or payable < await signoff_threshold_paise():
        return
    exact = await db.refund_signoffs.find_one({
        "cancellation_id": cancellation_id, "order_id": order_id, "amount_paise": payable,
        "status": "approved", "used_at": None})
    if exact:
        return
    larger = await db.refund_signoffs.find_one({
        "cancellation_id": cancellation_id, "order_id": order_id, "status": "approved", "used_at": None,
        "amount_paise": {"$gte": payable}}, sort=[("amount_paise", 1)])
    if larger:
        await db.refund_signoffs.update_one(
            {"_id": larger["_id"], "status": "approved", "used_at": None},
            {"$set": {"amount_paise": payable}})


class CancelIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)
    account_holder: str = Field(min_length=3, max_length=80)
    account_number: str
    ifsc: str
    bank_name: str = Field(min_length=3, max_length=80)

    @field_validator("account_number")
    @classmethod
    def acct(cls, v):
        if not re.fullmatch(r"\d{9,18}", v.strip()):
            raise ValueError("Account number must be 9-18 digits")
        return v.strip()

    @field_validator("ifsc")
    @classmethod
    def ifsc_ok(cls, v):
        if not IFSC.match(v.strip().upper()):
            raise ValueError("IFSC must look like ABCD0123456")
        return v.strip().upper()


def out(c: Cancellation) -> dict:
    return c.model_dump(exclude={"bank_ref"})


def build_timeline(status: str, refund_paise: int, threshold_paise: int) -> list[dict]:
    large = (refund_paise >= threshold_paise and refund_paise > 0) or status in ("pending_signoff", "signoff_rejected")

    def step(key: str, label: str, state: str) -> dict:
        return {"key": key, "label": label, "state": state}

    steps = [step("submitted", "Request submitted", "done")]
    if status == "requested":
        steps.append(step("review", "Under review", "current"))
        steps.append(step("approved", "Approved", "upcoming"))
        if large:
            steps.append(step("signoff", "Finance sign-off", "upcoming"))
        if refund_paise > 0:
            steps.append(step("credited", "Refund credited", "upcoming"))
        return steps
    if status == "rejected":
        steps.append(step("review", "Rejected", "current"))
        return steps
    steps.append(step("review", "Under review", "done"))
    if status == "closed" and refund_paise <= 0:
        steps.append(step("decision", "No refund due", "done"))
        return steps
    steps.append(step("approved", "Approved", "done"))
    if large:
        if status == "pending_signoff":
            steps.append(step("signoff", "Finance sign-off", "current"))
            steps.append(step("credited", "Refund credited", "upcoming"))
            return steps
        if status == "signoff_rejected":
            steps.append(step("signoff", "Sign-off declined", "current"))
            return steps
        steps.append(step("signoff", "Finance sign-off", "done"))
    if status == "refunded":
        steps.append(step("credited", "Refund credited", "done"))
    elif status == "refund_failed":
        steps.append(step("credited", "Refund failed", "current"))
    else:
        steps.append(step("credited", "Refund credited", "upcoming"))
    return steps


async def present(c: Cancellation) -> dict:
    data = out(c)
    data["quote"] = await refresh_quote(c.quote, c.candidate_id, c.id)
    refund_paise = int((data["quote"] or {}).get("refund_paise") or 0)
    data["timeline"] = build_timeline(c.status, refund_paise, await signoff_threshold_paise())
    return data


@router.post("/candidate/cancellation")
async def request_cancellation(body: CancelIn, request: Request, user: User = Depends(require_candidate)):
    seat = Allotment.from_mongo(await db.partb_allotments.find_one({"candidate_id": user.id, "seat_held": True}))
    if not seat:
        raise err(409, "no_seat", "You do not hold a seat to cancel")
    if await db.cancellations.find_one({"candidate_id": user.id, "status": "requested"}):
        raise err(409, "already_requested", "A cancellation request is already under review")
    bank_ref = str((await db.bank_details.insert_one({"candidate_id": user.id, "holder": body.account_holder, "number": body.account_number,
                                                      "ifsc": body.ifsc, "bank_name": body.bank_name, "created_at": now_utc()})).inserted_id)
    c = Cancellation(cycle_id=seat.cycle_id, cancellation_ref=_ref("WS-CXL"), candidate_id=user.id, application_ref=seat.application_ref,
                     allotment_id=seat.id, program_code=seat.program_code, reason=body.reason.strip(), bank_ref=bank_ref,
                     bank={"holder": body.account_holder, "number": "X" * (len(body.account_number) - 4) + body.account_number[-4:],
                           "ifsc": body.ifsc, "bank_name": body.bank_name},
                     quote=await quote(user.id), history=[{"action": "requested", "by": user.email, "at": now_utc()}])
    try:
        c.id = str((await db.cancellations.insert_one(c.to_mongo())).inserted_id)
    except Exception:
        raise err(409, "already_requested", "A cancellation request is already under review")
    await audit(request, user, "cancellation.requested", "cancellation", c.id, after={"program_code": c.program_code, "reason": c.reason})
    await notify(user.id, "cancellation", "Cancellation requested", f"Request {c.cancellation_ref} is under review.")
    return await present(c)


@router.get("/candidate/cancellation")
async def my_cancellation(user: User = Depends(require_candidate)):
    c = Cancellation.from_mongo(await db.cancellations.find_one({"candidate_id": user.id}, sort=[("created_at", -1)]))
    seat = await db.partb_allotments.find_one({"candidate_id": user.id, "seat_held": True})
    return {"cancellation": await present(c) if c else None, "can_request": bool(seat) and not (c and c.status == "requested"),
            "seat": {"program_code": seat["program_code"], "status": seat["status"]} if seat else None,
            "estimate": await quote(user.id) if seat else None}


async def cancellation_pdf(c: Cancellation) -> tuple[bytes, str]:
    u = await db.users.find_one({"_id": ObjectId(c.candidate_id)})
    ref = f"{c.cancellation_ref}-{c.status}"
    payload = c.model_dump()
    payload["quote"] = await refresh_quote(c.quote, c.candidate_id, c.id)
    return pdf_service.cancellation_receipt_pdf({"name": u["name"], "candidate_ref": u.get("candidate_ref"), "application_ref": c.application_ref},
                                                payload, ref), ref


@router.get("/candidate/cancellation/receipt")
async def my_cancellation_receipt(user: User = Depends(require_candidate)):
    c = Cancellation.from_mongo(await db.cancellations.find_one({"candidate_id": user.id, "status": {"$in": ["approved", "pending_signoff", "refunded", "refund_failed", "closed"]}},
                                                                sort=[("created_at", -1)]))
    if not c:
        raise err(409, "not_approved", "The cancellation receipt is available after approval")
    data, ref = await cancellation_pdf(c)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{ref}.pdf"'})


async def _get(cid: str) -> Cancellation:
    c = Cancellation.from_mongo(await db.cancellations.find_one({"_id": ObjectId(cid)})) if ObjectId.is_valid(cid) else None
    if not c:
        raise err(404, "not_found", "Cancellation not found")
    return c


class ReviewIn(BaseModel):
    remarks: str = Field(min_length=5, max_length=300)


@router.post("/partb/cancellations/{cid}/approve")
async def approve(cid: str, body: ReviewIn, request: Request, user: User = Depends(require("cancellations.review"))):
    c = await _get(cid)
    q = await quote(c.candidate_id)
    doc = await db.cancellations.find_one_and_update({"_id": ObjectId(c.id), "status": "requested"}, {"$set": {
        "status": "approved", "quote": q, "review_remarks": body.remarks, "reviewed_by": user.email, "reviewed_at": now_utc(), "updated_at": now_utc()},
        "$push": {"history": {"action": "approved", "by": user.email, "at": now_utc(), "remarks": body.remarks}}})
    if not doc:
        raise err(409, "invalid_state", f"Cancellation is {c.status}")
    a = Allotment.from_mongo(await db.partb_allotments.find_one({"_id": ObjectId(c.allotment_id)}))
    released = False
    if a and a.seat_held:
        res = await db.partb_allotments.update_one({"_id": ObjectId(a.id), "seat_held": True, "version": a.version}, {
            "$set": {"status": "cancelled", "seat_held": False, "version": a.version + 1, "remarks": f"Cancellation {c.cancellation_ref}", "updated_at": now_utc()},
            "$push": {"history": _hist("cancelled", user, remarks=f"Cancellation {c.cancellation_ref}", version=a.version + 1)}})
        if res.modified_count:
            await release_seat(a.cycle_id, a.program_code, a.id, f"cancellation {c.cancellation_ref}")
            released = True
    final = "closed" if q["refund_paise"] <= 0 else "approved"
    if final == "approved" and q["refund_paise"] >= await signoff_threshold_paise() and q.get("order_id"):
        final = "pending_signoff"
        await open_signoff(order_id=q["order_id"], order_ref=c.cancellation_ref, amount_paise=q["refund_paise"],
                           reason=f"Cancellation {c.cancellation_ref}", requested_by=user.email, cancellation_id=c.id)
    await db.cancellations.update_one({"_id": ObjectId(c.id)}, {"$set": {"seat_released": released, "status": final}})
    await audit(request, user, "cancellation.approved", "cancellation", c.id, before={"status": "requested"},
                after={"status": final, "seat_released": released, "refund_paise": q["refund_paise"]}, reason=body.remarks)
    if final == "pending_signoff":
        message = (f"Your seat in {c.program_code} is cancelled. The refund of ₹{q['refund_paise'] / 100:,.2f} "
                   "is waiting for Super Admin sign-off.")
    else:
        message = f"Your seat in {c.program_code} is cancelled. Refund due: ₹{q['refund_paise'] / 100:,.2f} ({q['tier']})."
    await notify(c.candidate_id, "cancellation", "Cancellation approved", message, email=True)
    return await present(await _get(cid))


@router.post("/partb/cancellations/{cid}/reject")
async def reject(cid: str, body: ReviewIn, request: Request, user: User = Depends(require("cancellations.review"))):
    c = await _get(cid)
    res = await db.cancellations.update_one({"_id": ObjectId(c.id), "status": "requested"}, {"$set": {
        "status": "rejected", "review_remarks": body.remarks, "reviewed_by": user.email, "reviewed_at": now_utc(), "updated_at": now_utc()},
        "$push": {"history": {"action": "rejected", "by": user.email, "at": now_utc(), "remarks": body.remarks}}})
    if not res.modified_count:
        raise err(409, "invalid_state", f"Cancellation is {c.status}")
    await audit(request, user, "cancellation.rejected", "cancellation", c.id, reason=body.remarks)
    await notify(c.candidate_id, "cancellation", "Cancellation request rejected", body.remarks, email=True)
    return await present(await _get(cid))


class StepUpIn(BaseModel):
    otp_challenge_id: str
    otp_code: str = Field(min_length=6, max_length=6)


@router.post("/accounts/cancellations/{cid}/refund")
async def refund(cid: str, body: StepUpIn, request: Request, user: User = Depends(require("payments.refund"))):
    c = await _get(cid)
    q = await refresh_quote(c.quote, c.candidate_id, c.id) if c.status in ("approved", "refund_failed") else c.quote
    if c.status not in ("approved", "refund_failed") or not q or not q.get("refund_paise") or not q.get("order_id"):
        if q and int(q.get("already_refunded_paise") or 0) and c.status in ("approved", "refund_failed"):
            raise err(409, "not_refundable", "Earlier refunds already cover the amount due under the refund policy")
        raise err(409, "not_refundable", "Only approved cancellations with a refund due can be refunded")
    await _align_approved_signoff(c.id, q["order_id"], q["refund_paise"])
    r = await execute_refund(q["order_id"], q["refund_paise"] / 100, f"Cancellation {c.cancellation_ref}",
                             f"cancel-{c.id}-{q['refund_paise']}",
                             request, user, (body.otp_challenge_id, body.otp_code))
    ok = r["refund"]["status"] == "succeeded"
    await db.cancellations.update_one({"_id": ObjectId(c.id)}, {"$set": {
        "status": "refunded" if ok else "refund_failed", "refund_id": r["refund"]["id"], "refund_status": r["refund"]["status"], "updated_at": now_utc()},
        "$push": {"history": {"action": "refund_" + r["refund"]["status"], "by": user.email, "at": now_utc()}}})
    if ok:
        await notify(c.candidate_id, "refund", "Refund processed", f"₹{r['refund']['amount']:,.2f} refunded for {c.cancellation_ref}.", email=True)
    fresh = await present(await _get(cid))
    return {**fresh, "refund": r["refund"], "idempotent_replay": r["idempotent_replay"]}


async def _cancellation_rows(status: Optional[str], skip: int = 0, limit: Optional[int] = None) -> list[dict]:
    query = {"status": status} if status else {}
    cursor = db.cancellations.find(query).sort("created_at", -1).skip(skip)
    if limit is not None:
        cursor = cursor.limit(limit)
    docs = await cursor.to_list(limit or 500)
    cids = list({d["candidate_id"] for d in docs})
    user_ids = [ObjectId(c) for c in cids if ObjectId.is_valid(c)]
    users = {str(u["_id"]): u async for u in db.users.find({"_id": {"$in": user_ids}}, {"name": 1, "candidate_ref": 1})} if user_ids else {}
    orders_by: dict[str, list] = {}
    if cids:
        async for order in db.payment_orders.find({"candidate_id": {"$in": cids}, "fee_code": "admission_fee", "status": "paid"}):
            orders_by.setdefault(order["candidate_id"], []).append(order)
    threshold = await signoff_threshold_paise()
    rows = []
    for d in docs:
        c = Cancellation.from_mongo(d)
        u = users.get(c.candidate_id, {})
        data = out(c)
        data["quote"] = await refresh_quote(c.quote, c.candidate_id, c.id, orders_by.get(c.candidate_id, []))
        data["timeline"] = build_timeline(c.status, int((data["quote"] or {}).get("refund_paise") or 0), threshold)
        rows.append({**data, "name": u.get("name"), "candidate_ref": u.get("candidate_ref")})
    return rows


@router.get("/partb/cancellations")
async def list_cancellations(status: Optional[str] = None, page: Optional[int] = None,
                             page_size: int = Query(50, ge=1, le=200),
                             _: User = Depends(require_any("cancellations.review", "payments.read", "partb.read"))):
    if page is None:
        return await _cancellation_rows(status)
    size = min(max(page_size, 1), 200)
    start = (max(page, 1) - 1) * size
    total = await db.cancellations.count_documents({"status": status} if status else {})
    return {"rows": await _cancellation_rows(status, start, size), "total": total, "page": max(page, 1), "page_size": size}


@router.get("/partb/cancellations/export")
async def export_cancellations(request: Request, user: User = Depends(require_any("cancellations.review", "payments.read", "partb.read"))):
    rows = await _cancellation_rows(None)
    mask = user.role == "auditor"
    await audit(request, user, "cancellations.exported", "export", None, after={"rows": len(rows), "masked": mask})
    head = ["Ref", "Candidate", "Application", "Program", "Status", "Reason", "Tier", "Paid", "Already refunded", "Deduction", "Refund due", "Seat released", "Bank", "Requested", "Reviewed by"]
    return xlsx_response([("Cancellations", head, [[r["cancellation_ref"], r["name"], r["application_ref"], r["program_code"], r["status"], r["reason"],
                                                    (r["quote"] or {}).get("tier"), (r["quote"] or {}).get("paid_paise", 0) / 100,
                                                    (r["quote"] or {}).get("already_refunded_paise", 0) / 100,
                                                    (r["quote"] or {}).get("deduction_paise", 0) / 100, (r["quote"] or {}).get("refund_paise", 0) / 100,
                                                    r["seat_released"], "masked" if mask else f"{r['bank']['bank_name']} {r['bank']['number']}",
                                                    r["created_at"].strftime("%Y-%m-%d"), r.get("reviewed_by") or ""] for r in rows])],
                         f"weschool-cancellations-{now_utc():%Y%m%d-%H%M}.xlsx")
