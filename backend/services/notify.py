import asyncio
import logging
from html import escape

from bson import ObjectId

from core import db, log_event, now_utc
from services.email_service import send_email

logger = logging.getLogger(__name__)


async def _mail(nid: ObjectId, to: str, title: str, body: str):
    try:
        await send_email(to=to, subject=f"WeSchool Admissions: {title}",
                         html=f"<p>{escape(body)}</p><p>Sign in to the WeSchool admissions portal for full details.</p>")
        status = "sent"
    except Exception as e:
        status = "failed"
        await log_event("email", "notification_failed", f"{title}: {str(e)[:160]}", level="error", meta={"to": to})
    await db.notifications.update_one({"_id": nid}, {"$set": {"email_status": status}})


async def notify(user_id: str, kind: str, title: str, body: str, email: bool = False):
    u = await db.users.find_one({"_id": ObjectId(user_id)}, {"email": 1})
    res = await db.notifications.insert_one({"user_id": user_id, "kind": kind, "title": title, "body": body, "read_at": None,
                                             "created_at": now_utc(), "email_status": "queued" if email else None})
    if email and u:
        asyncio.create_task(_mail(res.inserted_id, u["email"], title, body))
