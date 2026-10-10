"""Delete payment proofs and bank account numbers once the published retention window has passed."""
import logging
from datetime import timedelta
from pathlib import Path

from core import db, now_utc
from services import storage

logger = logging.getLogger(__name__)

RETENTION_DAYS = 365


async def purge_retained() -> dict:
    cutoff = now_utc() - timedelta(days=RETENTION_DAYS)
    proofs = banks = 0
    async for f in db.files.find({"kind": "payment_proof", "is_deleted": {"$ne": True}, "created_at": {"$lt": cutoff}}):
        if storage.LOCAL_DIR:
            path = (Path(storage.LOCAL_DIR) / f["storage_path"]).resolve()
            root = Path(storage.LOCAL_DIR).resolve()
            if root in path.parents or path == root:
                path.unlink(missing_ok=True)
        await db.files.update_one({"_id": f["_id"]}, {"$set": {"is_deleted": True, "quarantine": True, "purged_at": now_utc()}})
        proofs += 1
    res = await db.bank_details.update_many(
        {"created_at": {"$lt": cutoff}, "number": {"$exists": True}},
        {"$unset": {"number": ""}, "$set": {"purged_at": now_utc()}})
    banks = res.modified_count
    if proofs or banks:
        logger.info("retention removed %s proofs and %s bank numbers", proofs, banks)
    return {"proofs": proofs, "bank_numbers": banks, "retention_days": RETENTION_DAYS}
