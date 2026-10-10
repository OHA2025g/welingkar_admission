import asyncio
import logging
import os
from datetime import date, datetime, timedelta

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from core import IST, db, now_utc
from services.notify import notify
from services.reconcile import reconcile_books
from services.retention import purge_retained

logger = logging.getLogger(__name__)

MILESTONES = {7: "due_minus_7", 1: "due_minus_1", 0: "due_today", -1: "overdue_1"}
OPEN_CANCELLATION = ("requested", "pending_signoff", "approved", "refund_failed", "signoff_rejected")
LOOKBACK_DAYS = 8


def seconds_until_next_run() -> float:
    now = datetime.now(IST)
    nxt = now.replace(hour=0, minute=10, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return max(60.0, (nxt - now).total_seconds())


def _copy(milestone: str, due: date, amount: float, programme: str, origin: str) -> tuple[str, str]:
    due_label = due.strftime("%d %b %Y")
    link = f"{origin}/candidate/admission-fee"
    if milestone == "due_today":
        return ("Admission fee is due today",
                f"Your admission fee of ₹{amount:,.0f} for {programme} is due today ({due_label}). Pay here: {link}")
    if milestone == "overdue_1":
        return ("Admission fee is overdue",
                f"Your admission fee of ₹{amount:,.0f} for {programme} was due on {due_label} and is now overdue. Pay here: {link}")
    return ("Admission fee due soon",
            f"Your admission fee of ₹{amount:,.0f} for {programme} is due on {due_label}. Pay from the admission fee page: {link}")


async def run_fee_reminders(on: date | None = None) -> dict:
    today = on or datetime.now(IST).date()
    cycle = await db.cycles.find_one({"status": "active"})
    due_raw = (cycle or {}).get("admission_fee_due")
    if not due_raw:
        return {"sent": 0, "milestone": None, "due_date": None, "recipients": []}
    due = date.fromisoformat(due_raw)
    milestone = MILESTONES.get((due - today).days)
    if not milestone:
        return {"sent": 0, "milestone": None, "due_date": due.isoformat(), "recipients": []}
    origin = (os.environ.get("CORS_ORIGINS") or "http://localhost:9150").split(",")[0].rstrip("/")
    amount = float(cycle.get("admission_fee_inr") or 0)
    sent, recipients = 0, []
    cursor = db.partb_allotments.find({"seat_held": True, "status": {"$in": ["allotted", "provisional"]}})
    async for seat in cursor:
        cid = seat["candidate_id"]
        if await db.payment_orders.find_one({"candidate_id": cid, "fee_code": "admission_fee", "status": "paid"}):
            continue
        if await db.cancellations.find_one({"candidate_id": cid, "status": {"$in": list(OPEN_CANCELLATION)}}):
            continue
        try:
            await db.fee_reminders.insert_one({
                "candidate_id": cid, "due_date": due.isoformat(), "milestone": milestone, "sent_at": now_utc()})
        except DuplicateKeyError:
            continue
        programme = seat.get("program_code") or "your programme"
        title, body = _copy(milestone, due, amount, programme, origin)
        await notify(cid, "fee_reminder", title, body, email=True)
        user = await db.users.find_one({"_id": ObjectId(cid)}, {"email": 1})
        recipients.append((user or {}).get("email"))
        sent += 1
    return {"sent": sent, "milestone": milestone, "due_date": due.isoformat(), "recipients": [e for e in recipients if e]}


async def catch_up_reminders() -> dict:
    """Send any milestone missed while the process was down, then record today."""
    today = datetime.now(IST).date()
    doc = await db.job_runs.find_one({"_id": "fee_reminders"})
    last = date.fromisoformat(doc["last_date"]) if doc and doc.get("last_date") else today - timedelta(days=1)
    day = max(last + timedelta(days=1), today - timedelta(days=LOOKBACK_DAYS))
    sent = 0
    while day <= today:
        result = await run_fee_reminders(day)
        sent += result["sent"]
        day += timedelta(days=1)
    await db.job_runs.update_one({"_id": "fee_reminders"}, {"$set": {"last_date": today.isoformat(), "at": now_utc()}}, upsert=True)
    return {"sent": sent, "through": today.isoformat()}


async def nightly_once() -> None:
    today = datetime.now(IST).date().isoformat()
    doc = await db.job_runs.find_one({"_id": "nightly"})
    if doc and doc.get("last_date") == today:
        return
    try:
        await purge_retained()
    except Exception:
        logger.exception("retention purge failed")
    try:
        result = await reconcile_books("nightly")
        if result["flags"]:
            body = f"Nightly reconciliation found {len(result['flags'])} item(s). Open Accounts → Reconciliation."
            async for user in db.users.find({"role": "accounts_operator", "status": "active"}, {"_id": 1}):
                await notify(str(user["_id"]), "reconciliation", "Reconciliation needs a look", body, email=True)
    except Exception:
        logger.exception("nightly reconciliation failed")
    await db.job_runs.update_one({"_id": "nightly"}, {"$set": {"last_date": today, "at": now_utc()}}, upsert=True)


async def reminder_loop() -> None:
    await asyncio.sleep(2)
    while True:
        try:
            caught = await catch_up_reminders()
            if caught["sent"]:
                logger.info("fee reminders caught up: %s", caught)
            await nightly_once()
        except Exception:
            logger.exception("fee reminder run failed")
        await asyncio.sleep(seconds_until_next_run())
