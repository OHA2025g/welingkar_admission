import asyncio
from core import db

async def main():
    ids = [str(o["_id"]) async for o in db.payment_orders.find({"fee_code": "admission_fee"})]
    await db.refunds.delete_many({"order_id": {"$in": ids}})
    await db.payment_orders.delete_many({"fee_code": "admission_fee"})
    for c in ("cancellations", "bank_details", "reconciliation_runs", "seat_events", "notifications"):
        await db[c].delete_many({})
    for c in await db.list_collection_names():
        if c.startswith("partb_"):
            await db[c].delete_many({})
    await db.files.delete_many({"kind": {"$in": ["partb_doc", "payment_proof"]}})
    print("reset done")

asyncio.run(main())
