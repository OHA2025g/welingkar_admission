"""Compare recorded payments with the gateway. Shared by the Accounts button and the nightly job."""
import asyncio

from core import db, now_utc
from services import stripe_gateway as gw


async def _gateway_flag(o: dict):
    try:
        s = await asyncio.wait_for(gw.retrieve_session(o["provider_session_id"]), timeout=2.5)
    except Exception as e:
        return {"order_ref": o["order_ref"], "issue": "gateway_unreachable", "detail": str(e)[:120]}
    gp = s.payment_status == "paid"
    if gp and o["status"] not in ("paid", "duplicate_payment", "amount_mismatch"):
        return {"order_ref": o["order_ref"], "order_id": str(o["_id"]), "issue": "gateway_paid_record_unpaid", "detail": o["status"]}
    if not gp and o["status"] == "paid":
        return {"order_ref": o["order_ref"], "order_id": str(o["_id"]), "issue": "record_paid_gateway_unpaid", "detail": s.payment_status}
    if gp and s.amount_total != o["amount_paise"]:
        return {"order_ref": o["order_ref"], "order_id": str(o["_id"]), "issue": "amount_mismatch", "detail": f"{s.amount_total} vs {o['amount_paise']}"}
    return None


async def reconcile_books(actor_email: str) -> dict:
    flags = []
    rows = await db.payment_orders.find(
        {"provider": "stripe", "provider_session_id": {"$ne": None}, "status": {"$ne": "expired"}}
    ).sort("created_at", -1).limit(100).to_list(100)
    flags.extend(f for f in await asyncio.gather(*(_gateway_flag(o) for o in rows)) if f)
    checked = len(rows)
    async for o in db.payment_orders.find({"refunded_paise": {"$gt": 0}}):
        done = sum(r["amount_paise"] for r in await db.refunds.find({"order_id": str(o["_id"]), "status": "succeeded"}).to_list(100))
        if done != o["refunded_paise"] or o["refunded_paise"] > o["amount_paise"]:
            flags.append({"order_ref": o["order_ref"], "order_id": str(o["_id"]), "issue": "refund_total_mismatch", "detail": f"{done} vs {o['refunded_paise']}"})
    async for g in db.payment_orders.aggregate([{"$match": {"status": {"$in": ["paid", "duplicate_payment"]}, "candidate_id": {"$ne": None}}},
                                                {"$group": {"_id": {"c": "$candidate_id", "f": "$fee_code"}, "n": {"$sum": 1}, "refs": {"$push": "$order_ref"}}},
                                                {"$match": {"n": {"$gt": 1}}}]):
        flags.append({"order_ref": ", ".join(g["refs"]), "issue": "multiple_payments_same_fee", "detail": g["_id"]["f"]})
    run = {"checked": checked, "flags": flags, "by": actor_email, "at": now_utc()}
    rid = (await db.reconciliation_runs.insert_one(run)).inserted_id
    return {**{k: v for k, v in run.items() if k != "_id"}, "id": str(rid)}
