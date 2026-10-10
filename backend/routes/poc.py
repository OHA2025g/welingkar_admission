from datetime import datetime
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from core import BaseDocument, IntegrationEvent, db, now_utc
from routes.otp import EMAIL_TEST_SINK, MAX_ATTEMPTS, OTP_TTL_MIN, RESEND_COOLDOWN_S
from security import require
from services import pdf_service, stripe_gateway, whatsapp_service
from services.email_service import EMAIL_FROM_NAME

router = APIRouter(prefix="/api", tags=["poc"])

SAMPLE_REF = "WS-2027-PGDM-000123"


class PocApplication(BaseDocument):
    application_ref: str
    snapshot_version: int
    status: str
    cycle: str
    program: str
    specialisations: list[str]
    candidate_name: str
    email: str
    mobile: str
    dob: str
    gender: str
    category: str
    address: str
    education: list[dict]
    work: list[dict]
    exams: list[dict]
    submitted_at: Optional[datetime] = None
    created_at: datetime


@router.get("/")
async def root():
    return {"service": "WeSchool Admissions Portal API", "phase": 0}


@router.get("/poc/health")
async def health():
    return {
        "timezone": "Asia/Kolkata", "currency": "INR", "server_time": now_utc(),
        "email": {"provider": "resend", "configured": True, "from_name": EMAIL_FROM_NAME,
                  "test_sink": EMAIL_TEST_SINK},
        "whatsapp": {"provider": "twilio", "configured": whatsapp_service.is_configured(),
                     "missing": whatsapp_service.missing_vars(),
                     "mode": "MOCKED" if whatsapp_service.is_mocked() else "live_template",
                     "mocked": whatsapp_service.is_mocked()},
        "payments": stripe_gateway.mode(),
        "otp_policy": {"ttl_minutes": OTP_TTL_MIN, "resend_cooldown_seconds": RESEND_COOLDOWN_S,
                       "max_attempts": MAX_ATTEMPTS, "digits": 6},
    }


@router.get("/poc/events", dependencies=[Depends(require("payments.read"))])
async def events(channel: Optional[str] = None, limit: int = 100):
    q = {"channel": channel} if channel else {}
    return [IntegrationEvent.from_mongo(d).model_dump()
            async for d in db.integration_events.find(q).sort("at", -1).limit(min(limit, 300))]


@router.delete("/poc/events", dependencies=[Depends(require("payments.read"))])
async def clear_events():
    res = await db.integration_events.delete_many({})
    return {"deleted": res.deleted_count}


async def seed_sample_application():
    now = now_utc()
    app = PocApplication(
        application_ref=SAMPLE_REF, snapshot_version=1, status="submitted", cycle="Admissions 2027",
        program="PGDM (Full-time, 2 years)", specialisations=["Marketing", "Business Design", "Finance"],
        candidate_name="Aarav Mehta", email="aarav.mehta@example.com", mobile="+91 98765 43210",
        dob="14 Aug 2002", gender="Male", category="General",
        address="Flat 12B, Shanti Niketan, L. N. Road, Matunga, Mumbai 400019, Maharashtra",
        education=[{"level": "Class X", "board": "CBSE", "year": "2018", "score": "92.4%"},
                   {"level": "Class XII", "board": "Maharashtra State Board", "year": "2020", "score": "88.6%"},
                   {"level": "Graduation", "board": "University of Mumbai (B.Com)", "year": "2023", "score": "8.4 CGPA"}],
        work=[{"org": "Tata Consultancy Services", "role": "Business Analyst", "months": "22"}],
        exams=[{"exam": "CAT", "year": "2026", "score": "94.12 percentile"},
               {"exam": "XAT", "year": "2027", "score": "89.50 percentile"}],
        submitted_at=now, created_at=now)
    await db.poc_applications.update_one({"application_ref": SAMPLE_REF}, {"$setOnInsert": app.to_mongo()}, upsert=True)


@router.get("/poc/applications", dependencies=[Depends(require("candidates.read"))])
async def list_applications():
    return [PocApplication.from_mongo(d).model_dump() async for d in db.poc_applications.find().sort("created_at", -1)]


def _pdf(data: bytes, filename: str, inline: bool):
    disp = "inline" if inline else "attachment"
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'{disp}; filename="{filename}"', "Cache-Control": "no-store"})


@router.get("/pdf/application/{application_ref}", dependencies=[Depends(require("candidates.read"))])
async def application_pdf(application_ref: str, inline: bool = False):
    a = PocApplication.from_mongo(await db.poc_applications.find_one({"application_ref": application_ref}))
    if not a:
        raise HTTPException(404, {"code": "not_found", "message": "Application not found"})
    if a.status != "submitted":
        raise HTTPException(409, {"code": "not_submitted", "message": "Only submitted applications have a PDF"})
    return _pdf(pdf_service.application_summary_pdf(a.model_dump()), f"{a.application_ref}-summary.pdf", inline)


@router.get("/pdf/receipt/{order_id}", dependencies=[Depends(require("payments.read"))])
async def receipt(order_id: str, inline: bool = False):
    try:
        oid = ObjectId(order_id)
    except (InvalidId, TypeError):
        raise HTTPException(404, {"code": "not_found", "message": "Order not found"})
    o = await db.payment_orders.find_one({"_id": oid})
    if not o:
        raise HTTPException(404, {"code": "not_found", "message": "Order not found"})
    if o["status"] != "paid":
        raise HTTPException(409, {"code": "not_paid", "message": "Receipt is available only for verified payments"})
    refunds = await db.refunds.find({"order_id": order_id}).sort("created_at", 1).to_list(100)
    return _pdf(pdf_service.receipt_pdf(o, refunds), f"{o['order_ref']}-receipt.pdf", inline)
