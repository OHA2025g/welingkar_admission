"""Staff snapshots, shared notifications, and the policy text shown beside a candidate decision."""
import gzip
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from bson import json_util
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core import db, now_utc
from routes.partb_docs import checklist
from routes.policies import active_policy
from security import User, audit, current_user, err, require, require_candidate
from services.retention import RETENTION_DAYS
from services.storage import LOCAL_DIR

router = APIRouter(prefix="/api", tags=["operations"])

CONFIRM = "RESTORE WECHOOL"
SNAP_COLLECTIONS = (
    "users", "cycles", "programs", "applications", "payment_orders", "refunds", "refund_signoffs",
    "cancellations", "partb_allotments", "notifications", "policy_versions", "fee_reminders",
)
_NAME = re.compile(r"^snapshot-\d{8}-\d{6}\.json\.gz$")


def _dir() -> Path:
    root = Path(LOCAL_DIR or "/tmp/weschool-snapshots") / "snapshots"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _scrub(name: str, doc: dict) -> dict:
    if name == "users":
        doc.pop("password_hash", None)
    return doc


class RestoreIn(BaseModel):
    phrase: str = Field(min_length=1, max_length=40)


def _notes(user: User):
    return db.notifications.find({"user_id": user.id}).sort("created_at", -1).limit(50)


async def _note_page(user: User) -> dict:
    rows = [{**{k: v for k, v in n.items() if k != "_id"}, "id": str(n["_id"])} async for n in _notes(user)]
    return {"unread": sum(1 for n in rows if not n.get("read_at")), "items": rows}


@router.get("/notifications")
async def notifications(user: User = Depends(current_user)):
    return await _note_page(user)


@router.post("/notifications/read-all")
async def read_notifications(user: User = Depends(current_user)):
    await db.notifications.update_many({"user_id": user.id, "read_at": None}, {"$set": {"read_at": now_utc()}})
    return await _note_page(user)


@router.get("/candidate/help")
async def candidate_help(topic: Literal["fee", "cancellation", "documents"], user: User = Depends(require_candidate)):
    lines: list[str] = []
    title = "Active policy"
    if topic == "fee":
        cycle = await db.cycles.find_one({"status": "active"}) or {}
        _, rules = await active_policy("admission_rules")
        title = "Fees"
        lines.append(f"Application fee is ₹{float(cycle.get('application_fee_inr') or 0):,.0f}.")
        lines.append(f"Admission fee is ₹{float(cycle.get('admission_fee_inr') or 0):,.0f}.")
        if cycle.get("admission_fee_due"):
            lines.append(f"Due on {cycle['admission_fee_due']}.")
        lines.append("Offline modes: " + ", ".join(rules.get("offline_modes") or []) + ".")
        lines.append(f"Payment proofs are deleted {RETENTION_DAYS} days after they are stored.")
    elif topic == "cancellation":
        _, policy = await active_policy("refund_policy")
        title = "Refund policy"
        lines.append(f"Processing fee ₹{float(policy.get('processing_fee_inr') or 0):,.0f}.")
        lines.append(f"Refunds at or above ₹{float(policy.get('super_admin_signoff_above_inr') or 0):,.0f} need Super Admin sign-off.")
        for tier in policy.get("tiers") or []:
            lines.append(f"{tier.get('label')}: {tier.get('refund_percent')}% refund.")
        lines.append(f"Bank account numbers are deleted {RETENTION_DAYS} days after they are stored.")
    else:
        title = "Documents still required"
        app = await db.applications.find_one({"candidate_id": user.id}) or {}
        if not app.get("photo_file_id"):
            lines.append("Passport photo")
        if not app.get("signature_file_id"):
            lines.append("Signature")
        for stage in ("initial", "admission"):
            have = {d["doc_key"] async for d in db.partb_documents.find({"candidate_id": user.id, "stage": stage, "status": {"$ne": "discrepancy"}})}
            for item in await checklist(user.id, stage):
                if item["key"] not in have:
                    lines.append(item["label"])
        if not lines:
            lines.append("Every required document is on file.")
    return {"topic": topic, "title": title, "lines": lines, "retention_days": RETENTION_DAYS}


@router.post("/admin/snapshots")
async def create_snapshot(request: Request, user: User = Depends(require("users.manage"))):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"snapshot-{stamp}.json.gz"
    payload = {}
    for coll in SNAP_COLLECTIONS:
        payload[coll] = [_scrub(coll, doc) async for doc in db[coll].find()]
    raw = gzip.compress(json_util.dumps(payload).encode())
    (_dir() / name).write_bytes(raw)
    await audit(request, user, "ops.snapshot_created", "snapshot", name, after={"bytes": len(raw)})
    return {"name": name, "bytes": len(raw), "created_at": now_utc()}


@router.get("/admin/snapshots")
async def list_snapshots(_: User = Depends(require("users.manage"))):
    rows = []
    for path in sorted(_dir().glob("snapshot-*.json.gz"), reverse=True):
        if _NAME.match(path.name):
            rows.append({"name": path.name, "bytes": path.stat().st_size})
    return rows


@router.get("/admin/snapshots/{name}")
async def download_snapshot(name: str, _: User = Depends(require("users.manage"))):
    if not _NAME.match(name):
        raise err(404, "not_found", "Snapshot not found")
    path = _dir() / name
    if not path.is_file():
        raise err(404, "not_found", "Snapshot not found")
    return Response(path.read_bytes(), media_type="application/gzip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/admin/snapshots/{name}/restore")
async def restore_snapshot(name: str, body: RestoreIn, request: Request, user: User = Depends(require("users.manage"))):
    if body.phrase != CONFIRM:
        raise err(400, "confirmation_required", f"Type {CONFIRM} to restore this snapshot")
    if not _NAME.match(name):
        raise err(404, "not_found", "Snapshot not found")
    path = _dir() / name
    if not path.is_file():
        raise err(404, "not_found", "Snapshot not found")
    data = json_util.loads(gzip.decompress(path.read_bytes()))
    kept = {}
    async for existing in db.users.find({}, {"password_hash": 1}):
        if existing.get("password_hash"):
            kept[existing["_id"]] = existing["password_hash"]
    restored = []
    for coll, docs in data.items():
        if coll not in SNAP_COLLECTIONS or not isinstance(docs, list):
            continue
        await db[coll].delete_many({})
        if coll == "users":
            for doc in docs:
                if doc.get("_id") in kept:
                    doc["password_hash"] = kept[doc["_id"]]
                else:
                    doc["status"] = "disabled"
                    doc.pop("password_hash", None)
        if docs:
            await db[coll].insert_many(docs)
        restored.append(coll)
    await audit(request, user, "ops.snapshot_restored", "snapshot", name, after={"collections": restored})
    return {"restored": restored, "name": name}
