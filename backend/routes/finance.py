import re
import uuid
from datetime import date, datetime, time, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core import IST, client_ip, db, now_utc
from routes.application import active_cycle
from routes.otp import _mask, issue_challenge
from routes.payments import PaymentOrder, _ref, apply_session, open_checkout, refresh_open_checkouts
from routes.policies import active_policy
from security import User, audit, err, require, require_candidate
from services import pdf_service, storage
from services import stripe_gateway as gw
from services.notify import notify
from services.fee_reminders import run_fee_reminders
from services.reconcile import reconcile_books
from services.xlsx import xlsx_response

router = APIRouter(prefix="/api", tags=["finance"])
MAGIC = {b"%PDF": "application/pdf", b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png"}
TXN = re.compile(r"^[A-Za-z0-9\-/]{6,40}$")
EXCEPTIONS = ["amount_mismatch", "duplicate_payment", "failed", "rejected"]


def masked(user: User) -> bool:
    return user.role == "auditor"


async def seat_for_fee(cid: str) -> Optional[dict]:
    return await db.partb_allotments.find_one({"candidate_id": cid, "seat_held": True, "status": {"$in": ["allotted", "provisional"]}})


async def paid_admission(cid: str) -> Optional[dict]:
    return await db.payment_orders.find_one({"candidate_id": cid, "fee_code": "admission_fee", "status": "paid"})


async def fee_amount() -> int:
    c = await active_cycle()
    amt = int(round(c.admission_fee_inr * 100))
    if amt <= 0:
        raise err(409, "fee_not_configured", "Admission fee is not configured for this cycle")
    return amt


async def store_proof(owner: str, f: UploadFile) -> str:
    data = await f.read(2_000_001)
    if len(data) > 2_000_000 or len(data) < 1_000:
        raise err(422, "bad_size", "Proof must be between 1 KB and 2 MB")
    ctype = next((t for m, t in MAGIC.items() if data.startswith(m)), None)
    if not ctype:
        raise err(422, "invalid_type", "Proof must be a PDF, JPG or PNG")
    try:
        stored = await storage.put_object(f"{storage.APP_NAME}/proofs/{owner}/{uuid.uuid4().hex}", data, ctype)
    except Exception:
        raise err(503, "storage_unavailable", "Upload failed. Please try again.")
    return str((await db.files.insert_one({"owner_id": owner, "kind": "payment_proof", "storage_path": stored["path"], "content_type": ctype,
                                           "size": len(data), "original_filename": f.filename, "is_deleted": False,
                                           "quarantine": False, "downloadable": True, "created_at": now_utc()})).inserted_id)


def order_row(o: dict, mask: bool = False) -> dict:
    p = PaymentOrder.from_mongo(o).model_dump(exclude={"payload_hash", "idempotency_key", "checkout_url"})
    p["amount"] = p["amount_paise"] / 100
    p["refunded_amount"] = p["refunded_paise"] / 100
    if mask:
        p["candidate_email"] = _mask("email", p["candidate_email"])
        p["txn_ref"] = (p["txn_ref"][:2] + "****" + p["txn_ref"][-2:]) if p.get("txn_ref") else None
    return p


# ---------- candidate ----------
@router.get("/candidate/admission-fee")
async def my_admission_fee(user: User = Depends(require_candidate)):
    await refresh_open_checkouts(user.id, "admission_fee")
    seat = await seat_for_fee(user.id)
    c = await active_cycle()
    _, rules = await active_policy("admission_rules")
    orders = [order_row(o) async for o in db.payment_orders.find({"candidate_id": user.id, "fee_code": "admission_fee"}).sort("created_at", -1)]
    return {"eligible": bool(seat), "program_code": seat["program_code"] if seat else None, "amount": c.admission_fee_inr,
            "paid": any(o["status"] == "paid" for o in orders), "orders": orders, "offline_modes": rules["offline_modes"]}


class CheckoutIn(BaseModel):
    origin_url: str


async def _fee_guard(user: User) -> dict:
    seat = await seat_for_fee(user.id)
    if not seat:
        raise err(409, "no_allotment", "The admission fee is payable after a seat is allotted")
    if await paid_admission(user.id):
        raise err(409, "already_paid", "Your admission fee is already paid")
    if await db.payment_orders.find_one({"candidate_id": user.id, "fee_code": "admission_fee", "status": "awaiting_verification"}):
        raise err(409, "offline_pending", "An offline payment is awaiting verification by Accounts")
    return seat


@router.post("/candidate/admission-fee/checkout")
async def admission_checkout(body: CheckoutIn, request: Request, user: User = Depends(require_candidate)):
    seat = await _fee_guard(user)
    amt = await fee_amount()
    pending = PaymentOrder.from_mongo(await db.payment_orders.find_one(
        {"candidate_id": user.id, "fee_code": "admission_fee", "status": "pending"}, sort=[("created_at", -1)]))
    if pending and pending.provider_session_id:
        session = await gw.retrieve_session(pending.provider_session_id)
        if await apply_session(pending, session, "status_poll"):
            raise err(409, "already_paid", "Your admission fee is already paid")
        if session.status == "open":
            return {"checkout_url": pending.checkout_url, "order_id": pending.id, "reused": True}
    n = await db.payment_orders.count_documents({"candidate_id": user.id, "fee_code": "admission_fee"})
    order = await open_checkout(fee_code="admission_fee", description=f"WeSchool Admission Fee · {seat['program_code']}", amount_paise=amt,
                                name=user.name, email=user.email, application_ref=seat["application_ref"],
                                idempotency_key=f"admfee-{seat['_id']}-{n + 1}", origin=body.origin_url, request=request,
                                candidate_id=user.id, return_base="/candidate/admission-fee")
    await db.payment_orders.update_one({"_id": ObjectId(order["id"])}, {"$set": {"allotment_id": str(seat["_id"])}})
    await audit(request, user, "admission_fee.checkout_started", "payment_order", order["id"], after={"amount": order["amount"]})
    return {"checkout_url": order["checkout_url"], "order_id": order["id"], "reused": False}


async def _offline_order(user_id: str, name: str, email: str, seat: dict, amt: int, mode: str, txn_ref: str, txn_date: str,
                         proof: Optional[str], status: str, actor: str) -> PaymentOrder:
    if not TXN.match(txn_ref.strip()):
        raise err(422, "bad_txn_ref", "Transaction reference must be 6-40 letters, digits, '-' or '/'")
    if not re.match(r"^20\d{2}-[01]\d-[0-3]\d$", txn_date):
        raise err(422, "bad_date", "Transaction date must be YYYY-MM-DD")
    _, rules = await active_policy("admission_rules")
    if mode not in rules["offline_modes"]:
        raise err(422, "bad_mode", f"Mode must be one of {', '.join(rules['offline_modes'])}")
    if await db.payment_orders.find_one({"txn_ref": txn_ref.strip().upper(), "status": {"$ne": "rejected"}}):
        raise err(409, "duplicate_txn_ref", "This transaction reference is already recorded")
    now = now_utc()
    o = PaymentOrder(id=str(ObjectId()), order_ref=_ref("WS-OFF"), fee_code="admission_fee", description=f"WeSchool Admission Fee · {seat['program_code']}",
                     amount_paise=amt, candidate_name=name, candidate_email=email, candidate_id=user_id, application_ref=seat["application_ref"],
                     provider="offline", origin="offline", status=status, idempotency_key=f"offline-{uuid.uuid4().hex}", payload_hash="-",
                     allotment_id=str(seat["_id"]), offline_mode=mode, txn_ref=txn_ref.strip().upper(), txn_date=txn_date, proof_file_id=proof,
                     verified_via="accounts_offline" if status == "paid" else None, paid_at=now if status == "paid" else None,
                     reviewed_by=actor if status == "paid" else None, reviewed_at=now if status == "paid" else None,
                     created_at=now, updated_at=now)
    try:
        await db.payment_orders.insert_one(o.to_mongo())
    except DuplicateKeyError:
        raise err(409, "already_paid", "The admission fee is already paid")
    return o


@router.post("/candidate/admission-fee/offline")
async def submit_offline(request: Request, mode: str = Form(...), txn_ref: str = Form(...), txn_date: str = Form(...),
                         proof: Optional[UploadFile] = File(None), user: User = Depends(require_candidate)):
    seat = await _fee_guard(user)
    pid = await store_proof(user.id, proof) if proof else None
    o = await _offline_order(user.id, user.name, user.email, seat, await fee_amount(), mode, txn_ref, txn_date, pid, "awaiting_verification", user.email)
    await audit(request, user, "admission_fee.offline_submitted", "payment_order", o.id, after={"mode": mode, "txn_ref": o.txn_ref, "proof": bool(pid)})
    await notify(user.id, "payment", "Offline payment received", f"Reference {o.txn_ref} is awaiting verification by Accounts.")
    return order_row(o.to_mongo() | {"_id": ObjectId(o.id)})


# ---------- accounts ----------
async def _payment_summary(q: dict, rows: list[dict] | None = None) -> dict:
    if rows is not None:
        paid = [r for r in rows if r["status"] == "paid"]
        return {"orders": len(rows), "paid": len(paid), "collected": sum(r["amount"] for r in paid),
                "refunded": sum(r["refunded_amount"] for r in rows),
                "awaiting_verification": sum(r["status"] == "awaiting_verification" for r in rows),
                "exceptions": sum(r["status"] in EXCEPTIONS for r in rows)}
    orders = paid = collected = refunded = awaiting = exceptions = 0
    async for g in db.payment_orders.aggregate([
            {"$match": q},
            {"$group": {"_id": "$status", "n": {"$sum": 1}, "amount": {"$sum": "$amount_paise"}, "refunded": {"$sum": "$refunded_paise"}}}]):
        orders += g["n"]
        refunded += (g.get("refunded") or 0) / 100
        if g["_id"] == "paid":
            paid += g["n"]
            collected += (g.get("amount") or 0) / 100
        if g["_id"] == "awaiting_verification":
            awaiting += g["n"]
        if g["_id"] in EXCEPTIONS:
            exceptions += g["n"]
    return {"orders": orders, "paid": paid, "collected": collected, "refunded": refunded,
            "awaiting_verification": awaiting, "exceptions": exceptions}


@router.get("/accounts/payments")
async def payments_report(fee_code: Optional[str] = None, status: Optional[str] = None, origin: Optional[str] = None,
                          page: Optional[int] = None, page_size: int = 50,
                          user: User = Depends(require("payments.read"))):
    q = {**({"fee_code": fee_code} if fee_code else {}), **({"status": status} if status else {}), **({"origin": origin} if origin else {})}
    cursor = db.payment_orders.find(q).sort("created_at", -1)
    if page is None:
        rows = [order_row(o, masked(user)) async for o in cursor.limit(500)]
        return {"rows": rows, "summary": await _payment_summary(q, rows), "masked": masked(user)}
    size = min(max(page_size, 1), 200)
    start = (max(page, 1) - 1) * size
    total = await db.payment_orders.count_documents(q)
    rows = [order_row(o, masked(user)) async for o in cursor.skip(start).limit(size)]
    return {"rows": rows, "summary": await _payment_summary(q), "masked": masked(user),
            "total": total, "page": max(page, 1), "page_size": size}


@router.get("/accounts/payments/export")
async def payments_export(request: Request, user: User = Depends(require("payments.read"))):
    rows = (await payments_report(user=user))["rows"]
    await audit(request, user, "payments.exported", "export", None, after={"rows": len(rows), "masked": masked(user)})
    head = ["Order ref", "Fee", "Origin", "Status", "Amount", "Refunded", "Candidate", "Email", "Application", "Mode", "Txn ref", "Paid at", "Verified via"]
    return xlsx_response([("Payments", head, [[r["order_ref"], r["fee_code"], r["origin"], r["status"], r["amount"], r["refunded_amount"],
                                               r["candidate_name"], r["candidate_email"], r["application_ref"], r.get("offline_mode"), r.get("txn_ref"),
                                               r["paid_at"].strftime("%Y-%m-%d %H:%M") if r.get("paid_at") else "", r.get("verified_via")] for r in rows])],
                         f"weschool-payments{'-masked' if masked(user) else ''}-{now_utc():%Y%m%d-%H%M}.xlsx")


async def _offline(oid: str, status: str) -> dict:
    o = await db.payment_orders.find_one({"_id": ObjectId(oid), "origin": "offline"}) if ObjectId.is_valid(oid) else None
    if not o:
        raise err(404, "not_found", "Offline payment not found")
    if o["status"] != status:
        raise err(409, "invalid_state", f"Payment is {o['status']}")
    return o


@router.post("/accounts/payments/{oid}/verify")
async def verify_offline(oid: str, request: Request, proof: Optional[UploadFile] = File(None), user: User = Depends(require("payments.verify"))):
    o = await _offline(oid, "awaiting_verification")
    pid = await store_proof(o["candidate_id"], proof) if proof else o.get("proof_file_id")
    if not pid:
        raise err(422, "proof_required", "Attach payment proof before marking an offline payment as paid")
    now = now_utc()
    try:
        res = await db.payment_orders.update_one({"_id": o["_id"], "status": "awaiting_verification"}, {"$set": {
            "status": "paid", "paid_at": now, "proof_file_id": pid, "verified_via": "offline_verified", "reviewed_by": user.email,
            "reviewed_at": now, "updated_at": now}})
    except DuplicateKeyError:
        raise err(409, "already_paid", "The candidate already has a paid admission fee. Reject this entry instead.")
    if not res.modified_count:
        raise err(409, "stale", "Payment was reviewed meanwhile")
    await audit(request, user, "payment.offline_verified", "payment_order", oid, before={"status": "awaiting_verification"}, after={"status": "paid"})
    await notify(o["candidate_id"], "payment", "Admission fee verified", f"Your offline payment {o['txn_ref']} is verified.", email=True)
    return order_row(await db.payment_orders.find_one({"_id": o["_id"]}))


class RejectIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


@router.post("/accounts/payments/{oid}/reject")
async def reject_offline(oid: str, body: RejectIn, request: Request, user: User = Depends(require("payments.verify"))):
    o = await _offline(oid, "awaiting_verification")
    res = await db.payment_orders.update_one({"_id": o["_id"], "status": "awaiting_verification"}, {"$set": {
        "status": "rejected", "failure_reason": body.reason, "reviewed_by": user.email, "reviewed_at": now_utc(), "updated_at": now_utc()}})
    if not res.modified_count:
        raise err(409, "stale", "Payment was reviewed meanwhile")
    await audit(request, user, "payment.offline_rejected", "payment_order", oid, after={"status": "rejected"}, reason=body.reason)
    await notify(o["candidate_id"], "payment", "Offline payment rejected", f"Reference {o['txn_ref']}: {body.reason}", email=True)
    return order_row(await db.payment_orders.find_one({"_id": o["_id"]}))


@router.post("/accounts/payments/offline")
async def record_offline(request: Request, application_ref: str = Form(...), mode: str = Form(...), txn_ref: str = Form(...),
                         txn_date: str = Form(...), amount: float = Form(...), proof: UploadFile = File(...),
                         user: User = Depends(require("payments.verify"))):
    app = await db.applications.find_one({"application_ref": application_ref.strip()})
    seat = await seat_for_fee(app["candidate_id"]) if app else None
    if not seat:
        raise err(404, "no_allotment", "No allotted seat for this application reference")
    amt = await fee_amount()
    if int(round(amount * 100)) != amt:
        raise err(422, "amount_mismatch", f"Amount must equal the admission fee (₹{amt / 100:,.0f})")
    if await paid_admission(app["candidate_id"]):
        raise err(409, "already_paid", "The admission fee is already paid")
    u = await db.users.find_one({"_id": ObjectId(app["candidate_id"])})
    pid = await store_proof(app["candidate_id"], proof)
    o = await _offline_order(app["candidate_id"], u["name"], u["email"], seat, amt, mode, txn_ref, txn_date, pid, "paid", user.email)
    await audit(request, user, "payment.offline_recorded", "payment_order", o.id, after={"application_ref": application_ref, "txn_ref": o.txn_ref})
    await notify(app["candidate_id"], "payment", "Admission fee recorded", f"Accounts recorded your payment {o.txn_ref}.", email=True)
    return order_row(o.to_mongo() | {"_id": ObjectId(o.id)})


@router.get("/accounts/exceptions")
async def exceptions(user: User = Depends(require("payments.read"))):
    _, rules = await active_policy("admission_rules")
    stale = now_utc() - timedelta(days=rules["offline_verification_sla_days"])
    rows = [order_row(o, masked(user)) | {"exception": o["status"]} async for o in db.payment_orders.find({"status": {"$in": EXCEPTIONS}})]
    rows += [order_row(o, masked(user)) | {"exception": "verification_overdue"} async for o in
             db.payment_orders.find({"status": "awaiting_verification", "created_at": {"$lt": stale}})]
    refunds = [{k: v for k, v in r.items() if k != "_id"} | {"id": str(r["_id"])} async for r in db.refunds.find({"status": "failed"})]
    return {"orders": rows, "failed_refunds": refunds}


@router.post("/accounts/step-up/send")
async def step_up_send(request: Request, user: User = Depends(require("payments.refund"))):
    out = await issue_challenge("email", user.email, "step_up_refund", client_ip(request))
    await audit(request, user, "refund.step_up_sent", "otp_challenge", out["challenge_id"] if "challenge_id" in out else out.get("id"))
    return out


@router.post("/accounts/reconciliation/run")
async def run_reconciliation(request: Request, user: User = Depends(require("payments.refund"))):
    run = await reconcile_books(user.email)
    await audit(request, user, "payments.reconciled", "reconciliation", run["id"], after={"checked": run["checked"], "flags": len(run["flags"])})
    return run


@router.get("/accounts/reconciliation")
async def list_reconciliation(_: User = Depends(require("payments.read"))):
    return [{**{k: v for k, v in r.items() if k != "_id"}, "id": str(r["_id"])} async for r in db.reconciliation_runs.find().sort("at", -1).limit(10)]


def _sheet_day(raw: Optional[str]) -> date:
    if not raw:
        return datetime.now(IST).date()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise err(422, "bad_date", "Use a date like 2026-10-06")


async def _programme_for(order: dict, cache: dict) -> str:
    aid = order.get("allotment_id")
    if aid and aid in cache:
        return cache[aid]
    label = "Application fee" if order.get("fee_code") == "application_fee" else "Unassigned"
    if aid and ObjectId.is_valid(str(aid)):
        seat = await db.partb_allotments.find_one({"_id": ObjectId(str(aid))}, {"program_code": 1})
        if seat:
            label = seat["program_code"]
    elif order.get("fee_code") == "admission_fee" and "·" in (order.get("description") or ""):
        label = order["description"].split("·")[-1].strip()
    if aid:
        cache[str(aid)] = label
    return label


async def build_daily_sheet(day: date) -> dict:
    start = datetime.combine(day, time.min, tzinfo=IST)
    window = {"$gte": start, "$lt": start + timedelta(days=1)}
    groups: dict[str, dict] = {}
    cache: dict[str, str] = {}

    def bucket(name: str) -> dict:
        return groups.setdefault(name, {"program_code": name, "collected_paise": 0, "collected_count": 0,
                                        "refunded_paise": 0, "refunded_count": 0})

    paid = {"status": "paid", "paid_at": window, "fee_code": {"$in": ["admission_fee", "application_fee"]}}
    async for order in db.payment_orders.find(paid):
        row = bucket(await _programme_for(order, cache))
        row["collected_paise"] += order["amount_paise"]
        row["collected_count"] += 1
    async for refund in db.refunds.find({"status": "succeeded", "updated_at": window}):
        order = await db.payment_orders.find_one({"_id": ObjectId(refund["order_id"])}) if ObjectId.is_valid(refund["order_id"]) else None
        row = bucket(await _programme_for(order, cache) if order else "Unassigned")
        row["refunded_paise"] += refund["amount_paise"]
        row["refunded_count"] += 1
    programmes = sorted(groups.values(), key=lambda r: r["program_code"])
    totals = {key: sum(r[key] for r in programmes) for key in ("collected_paise", "collected_count", "refunded_paise", "refunded_count")}
    return {"date": day.isoformat(), "programmes": programmes, "totals": totals}


@router.get("/accounts/daily-sheet")
async def daily_sheet(on: Optional[str] = None, _: User = Depends(require("payments.read"))):
    return await build_daily_sheet(_sheet_day(on))


@router.get("/accounts/daily-sheet/export")
async def daily_sheet_export(request: Request, on: Optional[str] = None, user: User = Depends(require("payments.read"))):
    sheet = await build_daily_sheet(_sheet_day(on))
    await audit(request, user, "payments.daily_sheet_exported", "export", sheet["date"], after={"rows": len(sheet["programmes"])})
    head = ["Programme", "Collections (count)", "Collections (INR)", "Refunds (count)", "Refunds (INR)"]
    rows = [[r["program_code"], r["collected_count"], r["collected_paise"] / 100, r["refunded_count"], r["refunded_paise"] / 100]
            for r in sheet["programmes"]]
    t = sheet["totals"]
    rows.append(["Total", t["collected_count"], t["collected_paise"] / 100, t["refunded_count"], t["refunded_paise"] / 100])
    return xlsx_response([("Daily sheet", head, rows)], f"weschool-collections-{sheet['date']}.xlsx")


@router.post("/accounts/fee-reminders/run")
async def fee_reminders_run(on: Optional[str] = None, _: User = Depends(require("cycles.write"))):
    day = _sheet_day(on) if on else None
    return await run_fee_reminders(day)


@router.get("/accounts/proof/{oid}")
async def proof_file(oid: str, user: User = Depends(require("payments.verify"))):
    o = await db.payment_orders.find_one({"_id": ObjectId(oid)}) if ObjectId.is_valid(oid) else None
    if not o or not o.get("proof_file_id"):
        raise err(404, "not_found", "No proof attached")
    return {"file_id": o["proof_file_id"]}



@router.get("/candidate/admission-fee/receipt")
async def admission_receipt(user: User = Depends(require_candidate)):
    o = await paid_admission(user.id)
    if not o:
        raise err(409, "not_paid", "Receipt is available after the admission fee is verified")
    data = pdf_service.receipt_pdf(o, await db.refunds.find({"order_id": str(o["_id"])}).to_list(50))
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{o["order_ref"]}.pdf"'})
