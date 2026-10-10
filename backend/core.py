import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated, Any, Optional
from zoneinfo import ZoneInfo

from bson import ObjectId
from dotenv import load_dotenv
from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pymongo import ReturnDocument

load_dotenv(Path(__file__).parent / ".env")

IST = ZoneInfo(os.environ["APP_TIMEZONE"])
client = AsyncIOMotorClient(os.environ["MONGO_URL"], tz_aware=True)
db = client[os.environ["DB_NAME"]]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ist_str(dt: Optional[datetime]) -> str:
    return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST") if dt else "-"


def inr(paise: int) -> str:
    rupees, p = divmod(int(paise), 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"INR {s}.{p:02d}"


PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: Optional[dict]):
        return cls.model_validate(doc) if doc else None

    def to_mongo(self) -> dict:
        d = self.model_dump(exclude={"id"})
        if self.id:
            d["_id"] = ObjectId(self.id)
        return d


class IntegrationEvent(BaseDocument):
    channel: str
    kind: str
    level: str = "info"
    message: str
    meta: dict[str, Any] = {}
    at: datetime = Field(default_factory=now_utc)


async def log_event(channel: str, kind: str, message: str, level: str = "info", meta: Optional[dict] = None):
    await db.integration_events.insert_one(
        IntegrationEvent(channel=channel, kind=kind, level=level, message=message, meta=meta or {}).to_mongo()
    )


async def rate_limited(key: str, limit: int, window_s: int) -> bool:
    now = now_utc()
    bucket = int(now.timestamp() // window_s)
    doc = await db.rate_limits.find_one_and_update(
        {"key": key, "bucket": bucket},
        {"$inc": {"count": 1}, "$setOnInsert": {"expire_at": now + timedelta(seconds=window_s * 2)}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["count"] > limit


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


async def ensure_indexes():
    await db.otp_challenges.create_index([("destination", 1), ("channel", 1), ("purpose", 1), ("created_at", -1)])
    await db.rate_limits.create_index([("key", 1), ("bucket", 1)], unique=True)
    await db.rate_limits.create_index("expire_at", expireAfterSeconds=0)
    await db.payment_orders.create_index("idempotency_key", unique=True)
    try:
        await db.payment_orders.drop_index("provider_session_id_1")
    except Exception:
        pass
    await db.payment_orders.create_index("provider_session_id", unique=True, name="provider_session_uniq",
                                         partialFilterExpression={"provider_session_id": {"$type": "string"}})
    await db.payment_events.create_index("provider_event_id", unique=True)
    await db.refunds.create_index("idempotency_key", unique=True)
    await db.refunds.create_index("order_id")
    await db.refund_signoffs.create_index([("order_id", 1), ("amount_paise", 1), ("status", 1)])
    await db.fee_reminders.create_index([("candidate_id", 1), ("due_date", 1), ("milestone", 1)], unique=True)
    await db.poc_applications.create_index("application_ref", unique=True)
    await db.integration_events.create_index([("at", -1)])
