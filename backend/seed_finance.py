import logging
import uuid

from bson import ObjectId

from core import db, now_utc
from routes.allotment import Allotment
from routes.cancellation import Cancellation, quote
from routes.payments import PaymentOrder, _ref

logger = logging.getLogger(__name__)


async def ensure_finance_indexes():
    await db.payment_orders.create_index([("candidate_id", 1), ("fee_code", 1)], unique=True, name="one_paid_admission_fee",
                                         partialFilterExpression={"status": "paid", "fee_code": "admission_fee"})
    await db.cancellations.create_index("candidate_id", unique=True, name="one_open_cancellation",
                                        partialFilterExpression={"status": "requested"})


async def _order(i: int, u: dict, seat: dict, amt: int, status: str, origin: str, now) -> str:
    o = PaymentOrder(id=str(ObjectId()), order_ref=_ref("WS-PAY" if origin == "gateway" else "WS-OFF"), fee_code="admission_fee",
                     description=f"WeSchool Admission Fee · {seat['program_code']}", amount_paise=amt, candidate_name=u["name"],
                     candidate_email=u["email"], candidate_id=str(u["_id"]), application_ref=seat["application_ref"],
                     provider="stripe" if origin == "gateway" else "offline", origin=origin, status=status,
                     idempotency_key=f"seed-admfee-{i}-{uuid.uuid4().hex[:6]}", payload_hash="-", allotment_id=str(seat["_id"]),
                     offline_mode="neft" if origin == "offline" else None, txn_ref=f"NEFT2026SEED{i:02d}" if origin == "offline" else None,
                     txn_date=now.date().isoformat() if origin == "offline" else None,
                     verified_via="seed" if status == "paid" else None, paid_at=now if status == "paid" else None, created_at=now, updated_at=now)
    await db.payment_orders.insert_one(o.to_mongo())
    return o.id


async def seed_finance():
    if await db.payment_orders.find_one({"fee_code": "admission_fee"}):
        return
    cyc = await db.cycles.find_one({"code": "2026-28"})
    if not cyc:
        return
    if not cyc.get("admission_fee_inr"):
        await db.cycles.update_one({"_id": cyc["_id"]}, {"$set": {"admission_fee_inr": 150000}})
    amt = int(round((cyc.get("admission_fee_inr") or 150000) * 100))
    cid, now = str(cyc["_id"]), now_utc()
    users = {i: await db.users.find_one({"email": f"candidate{i:02d}@example.com"}) for i in (4, 11, 13)}
    if not all(users.values()):
        return
    for i, code in ((11, "PGDM-ME"), (13, "MMS-ACAP")):
        u = users[i]
        if await db.partb_allotments.find_one({"candidate_id": str(u["_id"]), "seat_held": True}):
            continue
        b = await db.partb_batches.find_one({"kind": "merit", "program_code": code, "status": "active"})
        elig = await db.partb_eligibility.find_one({"candidate_id": str(u["_id"]), "program_code": code, "status": "active"})
        if not b or not elig:
            logger.warning("seed_finance: Part B fixture missing")
            return
        a = Allotment(cycle_id=cid, candidate_id=str(u["_id"]), application_ref=elig["application_ref"], program_code=code, batch_id=str(b["_id"]),
                      batch_kind="merit", status="provisional", seat_held=True, receipt_version=1, created_by="admissions@weschool-demo.in",
                      history=[{"action": "provisional", "by": "admissions@weschool-demo.in", "at": now, "version": 1}])
        aid = str((await db.partb_allotments.insert_one(a.to_mongo())).inserted_id)
        await db.partb_seats.update_one({"cycle_id": cid, "program_code": code}, {"$inc": {"filled": 1}})
        await db.seat_events.insert_one({"program_code": code, "delta": 1, "reason": "seed allotment", "allotment_id": aid, "at": now})
    seats = {i: await db.partb_allotments.find_one({"candidate_id": str(users[i]["_id"]), "seat_held": True}) for i in users}
    await _order(4, users[4], seats[4], amt, "paid", "gateway", now)
    await _order(11, users[11], seats[11], amt, "paid", "gateway", now)
    await _order(13, users[13], seats[13], amt, "awaiting_verification", "offline", now)
    u = users[11]
    bank_ref = str((await db.bank_details.insert_one({"candidate_id": str(u["_id"]), "holder": u["name"], "number": "001234567890",
                                                      "ifsc": "HDFC0001234", "bank_name": "HDFC Bank", "created_at": now})).inserted_id)
    c = Cancellation(cycle_id=cid, cancellation_ref=_ref("WS-CXL"), candidate_id=str(u["_id"]), application_ref=seats[11]["application_ref"],
                     allotment_id=str(seats[11]["_id"]), program_code=seats[11]["program_code"],
                     reason="Joining a different institute closer to home for family reasons.", bank_ref=bank_ref,
                     bank={"holder": u["name"], "number": "XXXXXXXX7890", "ifsc": "HDFC0001234", "bank_name": "HDFC Bank"},
                     quote=await quote(str(u["_id"])), history=[{"action": "requested", "by": u["email"], "at": now}])
    await db.cancellations.insert_one(c.to_mongo())
    logger.info("Phase 5 finance seed complete")
