import io
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, ValidationError
from pymongo.errors import DuplicateKeyError

from app_schema import (DECLARATION_PGDM, ESSAYS, GRAD_DECL_VERSION, PIQ, SECTIONS, GraduationEligibility, Preferences,
                        _today)
from core import BaseDocument, IST, db, now_utc
from rbac import ROLE_PERMS
from routes.config import Cycle, Program, oid
from routes.payments import PaymentOrder, apply_session, open_checkout, refresh_open_checkouts
from routes.policies import active_policy
from security import User, audit, current_user, err, require_candidate, require_verified_candidate
from services import pdf_service, storage
from services import stripe_gateway as gw

router = APIRouter(prefix="/api", tags=["candidate-application"])
Image.MAX_IMAGE_PIXELS = 25_000_000
UPLOADS = {"photo": {"max": 200_000, "min": (200, 200), "label": "Photo"},
           "signature": {"max": 100_000, "min": (150, 50), "label": "Signature"}}
RESOURCES = [
    {"title": "Programme brochure 2026-28", "url": "https://www.welingkar.org/"},
    {"title": "Virtual campus tour (video)", "url": "https://www.youtube.com/@WeSchoolWelingkar"},
    {"title": "Admission process FAQs", "url": "https://www.welingkar.org/"},
]
NEWS = ["Applications for the 2026-28 batch are open.",
        "GA/PI schedules are published after application review.",
        "TFW applicants must upload a current-year family income certificate in Part B."]


class Application(BaseDocument):
    candidate_id: str
    cycle_id: str
    application_ref: str
    status: str = "draft"
    sections: dict[str, Any] = {}
    section_status: dict[str, str] = {}
    section_errors: dict[str, list] = {}
    photo_file_id: Optional[str] = None
    signature_file_id: Optional[str] = None
    submitted_at: Optional[datetime] = None
    submitted_version: int = 0
    post: dict[str, Any] = {}
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


FRIENDLY = {
    "roll_number": "Roll number must be 4-30 letters, digits, '-' or '/'",
    "pincode": "Enter a valid 6-digit PIN code",
    "emergency_contact_mobile": "Enter a valid 10-digit Indian mobile number",
    "alternate_mobile": "Enter a valid 10-digit Indian mobile number",
    "start": "Use the month picker (YYYY-MM)", "end": "Use the month picker (YYYY-MM)",
    "expected_completion": "Use the month picker (YYYY-MM)",
}


def _friendly(field: str, msg: str) -> str:
    last = field.split(".")[-1]
    if msg == "Field required":
        return "This field is required"
    if msg.startswith("String should match pattern"):
        return FRIENDLY.get(last, "Invalid format")
    if msg.startswith("Input should be a valid number") or msg.startswith("Input should be a valid integer"):
        return "Enter a number"
    if msg.startswith("Input should be") and "'" in msg:
        return "Choose one of the listed options"
    if msg.startswith("String should have at least"):
        return msg.replace("String should have", "Must have")
    return msg


def validation_errors(e: ValidationError) -> list[dict]:
    out = []
    for x in e.errors():
        msg = re.sub(r"^Value error, ", "", x["msg"])
        field = ".".join(str(p) for p in x["loc"])
        m = re.match(r"^([\w.]+): (.+)$", msg)
        if m:
            field = ".".join(filter(None, [field, m.group(1)]))
            msg = m.group(2)
        out.append({"field": field or "_", "message": _friendly(field, msg)})
    return out


async def validate_section(key: str, data: dict, cycle_id: str) -> tuple[Optional[dict], list[dict]]:
    try:
        clean = SECTIONS[key][1](**data).model_dump(mode="json")
    except ValidationError as e:
        return None, validation_errors(e)
    if key == "preferences":
        codes = {p["code"] async for p in db.programs.find({"cycle_id": cycle_id, "status": "active"}, {"code": 1})}
        bad = [c for c in clean["ranked"] if c not in codes]
        if bad:
            return None, [{"field": "ranked", "message": f"Unknown or inactive programme: {', '.join(bad)}"}]
    return clean, []


async def active_cycle() -> Cycle:
    c = Cycle.from_mongo(await db.cycles.find_one({"status": "active"}))
    if not c:
        raise err(409, "no_active_cycle", "No admission cycle is currently open")
    return c


def window_open(c: Cycle) -> bool:
    t = _today().isoformat()
    return c.application_open <= t <= c.application_close


async def fee_order(candidate_id: str) -> Optional[PaymentOrder]:
    return PaymentOrder.from_mongo(await db.payment_orders.find_one(
        {"candidate_id": candidate_id, "fee_code": "application_fee", "status": "paid"}))


async def get_or_create(user: User) -> Application:
    c = await active_cycle()
    app = Application.from_mongo(await db.applications.find_one({"candidate_id": user.id, "cycle_id": c.id}))
    if app:
        return app
    seq = await db.counters.find_one_and_update({"_id": f"app-{c.code}"}, {"$inc": {"seq": 1}}, upsert=True,
                                                return_document=True)
    app = Application(candidate_id=user.id, cycle_id=c.id, application_ref=f"WS-{c.code}-{seq['seq']:06d}")
    try:
        res = await db.applications.insert_one(app.to_mongo())
        app.id = str(res.inserted_id)
    except DuplicateKeyError:
        app = Application.from_mongo(await db.applications.find_one({"candidate_id": user.id, "cycle_id": c.id}))
    return app


def progress(app: Application, paid: bool) -> dict:
    done = sum(app.section_status.get(k) == "complete" for k in SECTIONS)
    items = len(SECTIONS) + 3
    score = done + bool(app.photo_file_id) + bool(app.signature_file_id) + paid
    return {"sections_complete": done, "sections_total": len(SECTIONS), "percent": round(100 * score / items),
            "photo": bool(app.photo_file_id), "signature": bool(app.signature_file_id), "fee_paid": paid}


async def app_out(app: Application, user: User) -> dict:
    paid = await fee_order(user.id)
    d = app.model_dump()
    d.update(progress=progress(app, bool(paid)), fee_paid=bool(paid),
             sections_meta=[{"key": k, "title": t} for k, (t, _) in SECTIONS.items()],
             post_config={"declaration": DECLARATION_PGDM, "essays": ESSAYS, "piq": PIQ,
                          "graduation_version": GRAD_DECL_VERSION})
    return d


class SectionIn(BaseModel):
    data: dict[str, Any]


@router.get("/candidate/admission-info")
async def admission_info(_: User = Depends(require_candidate)):
    c = await active_cycle()
    progs = [Program.from_mongo(p).model_dump(include={"code", "name", "route", "campus", "duration_months",
                                                        "seat_capacity", "tfw_seats", "stages", "application_fee_inr"})
             async for p in db.programs.find({"cycle_id": c.id, "status": "active"}).sort("name", 1)]
    tfw = await db.policy_versions.find_one({"key": "tfw_rules", "status": "active"})
    return {"cycle": c.model_dump(exclude={"version"}), "programs": progs, "news": NEWS, "resources": RESOURCES,
            "tfw": tfw["content"] if tfw else None, "window_open": window_open(c),
            "scholarships": ["Merit scholarships for top GA/PI performers (per institute policy)",
                             "Tuition Fee Waiver (TFW) seats under AICTE norms"]}


async def _pi_booking_cutoff(cycle_id: str, today) -> Optional[datetime]:
    """Next PI booking deadline: slot start minus the active cutoff, in Asia/Kolkata."""
    _, rules = await active_policy("selection_rules")
    hours = int(rules.get("pi_booking_cutoff_hours") or 0)
    now = datetime.now(IST)
    fallback = None
    query = {"cycle_id": cycle_id, "type": "PI", "status": "scheduled", "date": {"$gte": today.isoformat()}}
    async for raw in db.interview_sessions.find(query).sort([("date", 1), ("start", 1)]):
        start = datetime.fromisoformat(f"{raw['date']}T{raw['start']}").replace(tzinfo=IST)
        cutoff = start - timedelta(hours=hours)
        if fallback is None:
            fallback = cutoff
        if cutoff > now:
            return cutoff
    return fallback


@router.get("/candidate/dashboard")
async def candidate_dashboard(user: User = Depends(require_candidate)):
    c = Cycle.from_mongo(await db.cycles.find_one({"status": "active"}))
    verified = user.identity_status == "verified"
    app = Application.from_mongo(await db.applications.find_one({"candidate_id": user.id})) if verified else None
    paid = bool(await fee_order(user.id))
    p = progress(app, paid) if app else None
    submitted = app is not None and app.status == "submitted"
    form_done = p and p["sections_complete"] == p["sections_total"]

    def st(done, unlocked):
        return "done" if done else ("current" if unlocked else "locked")
    steps = [
        {"key": "register", "title": "Registration", "status": "done"},
        {"key": "verify", "title": "Email & WhatsApp verification", "status": st(verified, True)},
        {"key": "fee", "title": "Application fee", "status": st(paid, verified)},
        {"key": "form", "title": "Application form (7 sections)", "status": st(bool(form_done) or submitted, verified)},
        {"key": "documents", "title": "Photo & signature", "status": st(bool(p and p["photo"] and p["signature"]), verified)},
        {"key": "submit", "title": "Submit & download PDF", "status": st(submitted, verified and paid)},
        {"key": "post", "title": "Declarations, essays, PIQ & confirmation", "status": st(
            bool(app and app.post.get("confirmation")), submitted)},
    ]
    current = next((s for s in steps if s["status"] == "current"), None)
    step_path = {"verify": "/candidate/dashboard", "fee": "/candidate/payment", "form": "/candidate/application",
                 "documents": "/candidate/application", "submit": "/candidate/application", "post": "/candidate/after-submission"}
    documents = []
    if submitted and app:
        documents.append({"label": "Application", "path": "/candidate/application/pdf", "filename": f"{app.application_ref}.pdf"})
    if paid:
        documents.append({"label": "Application fee receipt", "path": "/candidate/application/fee/receipt", "filename": "application-fee-receipt.pdf"})
    if await db.payment_orders.find_one({"candidate_id": user.id, "fee_code": "admission_fee", "status": "paid"}):
        documents.append({"label": "Admission fee receipt", "path": "/candidate/admission-fee/receipt", "filename": "admission-fee-receipt.pdf"})
    if await db.partb_allotments.find_one({"candidate_id": user.id, "seat_held": True, "status": {"$in": ["allotted", "provisional"]}}):
        documents.append({"label": "Offer / allotment", "path": "/candidate/partb/allotment/receipt", "filename": "allotment-receipt.pdf"})
    if await db.cancellations.find_one({"candidate_id": user.id, "status": {"$in": ["approved", "pending_signoff", "refunded", "refund_failed", "closed"]}}):
        documents.append({"label": "Cancellation receipt", "path": "/candidate/cancellation/receipt", "filename": "cancellation-receipt.pdf"})
    today = datetime.now(IST).date()

    def days_until(raw):
        if not raw:
            return None
        return (datetime.fromisoformat(str(raw)[:10]).date() - today).days

    countdowns = []
    if c:
        for key, label, raw in (
            ("application_close", "Application closes", c.application_close),
            ("admission_fee_due", "Admission fee due", c.admission_fee_due),
        ):
            if raw:
                countdowns.append({"key": key, "label": label, "date": str(raw)[:10], "days": days_until(raw)})
        cutoff = await _pi_booking_cutoff(c.id, today)
        if cutoff:
            countdowns.append({"key": "pi_booking", "label": "PI booking closes", "date": cutoff.date().isoformat(),
                               "days": (cutoff.date() - today).days, "detail": cutoff.strftime("%H:%M") + " IST"})
    return {"user": user.public(), "cycle": c.model_dump(exclude={"version"}) if c else None, "steps": steps,
            "progress": p, "application_status": app.status if app else "not_started",
            "application_ref": app.application_ref if app else None,
            "next_step": {**current, "path": step_path.get(current["key"])} if current else None,
            "unread": await db.notifications.count_documents({"user_id": user.id, "read_at": None}),
            "countdowns": countdowns, "documents": documents,
            "saved_at": app.updated_at if app else None}


@router.get("/candidate/application")
async def get_application(user: User = Depends(require_verified_candidate)):
    return await app_out(await get_or_create(user), user)


@router.put("/candidate/application/sections/{key}")
async def save_section(key: str, body: SectionIn, user: User = Depends(require_verified_candidate)):
    if key not in SECTIONS:
        raise err(404, "unknown_section", "Unknown section")
    if len(str(body.data)) > 40_000:
        raise err(413, "too_large", "Section data is too large")
    app = await get_or_create(user)
    if app.status != "draft":
        raise err(409, "locked", "Your application is submitted and locked")
    clean, errors = await validate_section(key, body.data, app.cycle_id)
    status = "complete" if clean else ("in_progress" if body.data else "empty")
    res = await db.applications.update_one({"_id": ObjectId(app.id), "status": "draft"}, {"$set": {
        f"sections.{key}": clean or body.data, f"section_status.{key}": status,
        f"section_errors.{key}": errors, "updated_at": now_utc()}})
    if not res.matched_count:
        raise err(409, "locked", "Your application is submitted and locked")
    app = Application.from_mongo(await db.applications.find_one({"_id": ObjectId(app.id)}))
    return {"section": key, "status": status, "errors": errors, "saved_at": app.updated_at,
            "progress": progress(app, bool(await fee_order(user.id)))}


@router.post("/candidate/application/uploads/{kind}")
async def upload(kind: str, request: Request, file: UploadFile = File(...), user: User = Depends(require_verified_candidate)):
    rule = UPLOADS.get(kind)
    if not rule:
        raise err(404, "unknown_upload", "Unknown upload type")
    app = await get_or_create(user)
    if app.status != "draft":
        raise err(409, "locked", "Your application is submitted and locked")
    if file.content_type not in ("image/jpeg", "image/png"):
        raise err(422, "invalid_type", f"{rule['label']} must be a JPG or PNG image")
    data = await file.read(rule["max"] + 1)
    if len(data) > rule["max"]:
        raise err(422, "too_large", f"{rule['label']} must be {rule['max'] // 1000} KB or smaller")
    if len(data) < 2_000:
        raise err(422, "too_small", f"{rule['label']} file looks empty or corrupted")
    try:
        Image.open(io.BytesIO(data)).verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise err(422, "invalid_image", f"{rule['label']} is not a valid image file")
    if img.format not in ("JPEG", "PNG") or (img.format == "PNG") != (file.content_type == "image/png"):
        raise err(422, "type_mismatch", "File content does not match its type")
    w, h = img.size
    if w < rule["min"][0] or h < rule["min"][1]:
        raise err(422, "too_small_dimensions", f"{rule['label']} must be at least {rule['min'][0]}x{rule['min'][1]} px")
    if kind == "photo" and not (0.6 <= w / h <= 1.1):
        raise err(422, "bad_aspect", "Photo must be a portrait or square passport-style image")
    if kind == "signature" and w <= h:
        raise err(422, "bad_aspect", "Signature image must be wider than it is tall")
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=90)
    path = f"{storage.APP_NAME}/candidates/{user.id}/{kind}-{uuid.uuid4().hex}.jpg"
    try:
        stored = await storage.put_object(path, out.getvalue(), "image/jpeg")
    except Exception:
        raise err(503, "storage_unavailable", "Upload failed. Please try again.")
    fid = str(ObjectId())
    await db.files.insert_one({"_id": ObjectId(fid), "owner_id": user.id, "kind": kind, "storage_path": stored["path"],
                               "content_type": "image/jpeg", "size": len(out.getvalue()), "original_filename": file.filename,
                               "width": w, "height": h, "is_deleted": False, "quarantine": False, "downloadable": True,
                               "created_at": now_utc()})
    if getattr(app, f"{kind}_file_id"):
        await db.files.update_one({"_id": ObjectId(getattr(app, f"{kind}_file_id"))}, {"$set": {"is_deleted": True}})
    await db.applications.update_one({"_id": ObjectId(app.id)}, {"$set": {f"{kind}_file_id": fid, "updated_at": now_utc()}})
    await audit(request, user, f"application.{kind}_uploaded", "application", app.id, after={"file_id": fid, "size": len(data)})
    return {"file_id": fid, "kind": kind, "width": w, "height": h}


@router.get("/files/{file_id}")
async def get_file(file_id: str, user: User = Depends(current_user)):
    f = await db.files.find_one({"_id": oid(file_id)})
    if not f:
        raise err(404, "not_found", "File not found")
    ok = f["owner_id"] == user.id or "applications.read" in ROLE_PERMS[user.role]
    if not ok and "assessments.score" in ROLE_PERMS[user.role] and f["kind"] == "photo":
        sids = [str(s["_id"]) async for s in db.interview_sessions.find({"panelist_ids": user.id}, {"_id": 1})]
        ok = bool(await db.interview_bookings.find_one({"candidate_id": f["owner_id"], "status": "booked", "session_id": {"$in": sids}}))
    if not ok and f["kind"] == "partb_doc" and "documents.verify" in ROLE_PERMS[user.role]:
        ok = True
    if not ok or f.get("is_deleted") or f.get("quarantine"):
        raise err(404, "not_found", "File not found")
    data, _ = await storage.get_object(f["storage_path"])
    return Response(data, media_type=f["content_type"], headers={"Cache-Control": "private, no-store"})


class CheckoutIn(BaseModel):
    origin_url: str


@router.post("/candidate/application/fee/checkout")
async def fee_checkout(body: CheckoutIn, request: Request, user: User = Depends(require_verified_candidate)):
    c = await active_cycle()
    if not window_open(c):
        raise err(409, "window_closed", "The application window for this cycle is closed")
    if await fee_order(user.id):
        raise err(409, "already_paid", "Your application fee is already paid")
    app = await get_or_create(user)
    pending = PaymentOrder.from_mongo(await db.payment_orders.find_one(
        {"candidate_id": user.id, "fee_code": "application_fee", "status": "pending"}, sort=[("created_at", -1)]))
    if pending and pending.provider_session_id:
        session = await gw.retrieve_session(pending.provider_session_id)
        if await apply_session(pending, session, "status_poll"):
            raise err(409, "already_paid", "Your application fee is already paid")
        if session.status == "open":
            return {"checkout_url": pending.checkout_url, "order_id": pending.id, "reused": True}
    n = await db.payment_orders.count_documents({"candidate_id": user.id, "fee_code": "application_fee"})
    order = await open_checkout(
        fee_code="application_fee", description=f"WeSchool Application Fee ({c.code})",
        amount_paise=int(round(c.application_fee_inr * 100)), name=user.name, email=user.email,
        application_ref=app.application_ref, idempotency_key=f"appfee-{app.id}-{n + 1}", origin=body.origin_url,
        request=request, candidate_id=user.id, return_base="/candidate/payment")
    await audit(request, user, "fee.checkout_started", "payment_order", order["id"], after={"amount": order["amount"]})
    return {"checkout_url": order["checkout_url"], "order_id": order["id"], "reused": False}


@router.get("/candidate/application/fee")
async def fee_status(user: User = Depends(require_verified_candidate)):
    await refresh_open_checkouts(user.id)
    orders = [PaymentOrder.from_mongo(d).model_dump(include={"id", "order_ref", "amount_paise", "status", "paid_at",
                                                             "created_at", "verified_via"})
              async for d in db.payment_orders.find({"candidate_id": user.id}).sort("created_at", -1)]
    paid = await fee_order(user.id)
    c = await active_cycle()
    return {"paid": bool(paid), "paid_order_id": paid.id if paid else None, "amount": c.application_fee_inr,
            "orders": [{**o, "amount": o["amount_paise"] / 100} for o in orders], "window_open": window_open(c)}


@router.get("/candidate/application/fee/receipt")
async def fee_receipt(user: User = Depends(require_verified_candidate)):
    o = await db.payment_orders.find_one({"candidate_id": user.id, "fee_code": "application_fee", "status": "paid"})
    if not o:
        raise err(409, "not_paid", "Invoice is available after a verified payment")
    refunds = await db.refunds.find({"order_id": str(o["_id"])}).to_list(50)
    return Response(pdf_service.receipt_pdf(o, refunds), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{o["order_ref"]}-invoice.pdf"'})


async def snapshot(app: Application, user_doc: dict) -> dict:
    progs = {p["code"]: p["name"] async for p in db.programs.find({"cycle_id": app.cycle_id}, {"code": 1, "name": 1})}
    cycle = await db.cycles.find_one({"_id": ObjectId(app.cycle_id)})
    return {"application_ref": app.application_ref, "cycle_code": cycle["code"], "sections": app.sections,
            "preference_names": [progs.get(c, c) for c in app.sections.get("preferences", {}).get("ranked", [])],
            "photo_file_id": app.photo_file_id, "signature_file_id": app.signature_file_id,
            "candidate": {k: user_doc.get(k) for k in ("name", "email", "mobile", "candidate_ref", "state", "city")}}


async def write_version(app_id: str, version: int, snap: dict, reason: str, actor: str):
    await db.application_versions.insert_one({"application_id": app_id, "version": version, "snapshot": snap,
                                              "reason": reason, "created_by": actor, "created_at": now_utc()})


@router.post("/candidate/application/submit")
async def submit(request: Request, user: User = Depends(require_verified_candidate)):
    app = await get_or_create(user)
    if app.status == "submitted":
        raise err(409, "already_submitted", "Your application is already submitted")
    if not await fee_order(user.id):
        raise err(409, "fee_unpaid", "Pay the application fee before submitting")
    if not window_open(await active_cycle()):
        raise err(409, "window_closed", "The application window for this cycle is closed")
    problems = []
    for key, (title, _) in SECTIONS.items():
        _, errors = await validate_section(key, app.sections.get(key) or {}, app.cycle_id)
        if errors:
            problems.append({"section": key, "title": title, "errors": errors[:5]})
    for kind in ("photo", "signature"):
        if not getattr(app, f"{kind}_file_id"):
            problems.append({"section": kind, "title": UPLOADS[kind]["label"], "errors": [{"field": "_", "message": "Upload required"}]})
    if problems:
        raise err(422, "incomplete", "Complete all sections before submitting", problems=problems)
    now = now_utc()
    res = await db.applications.update_one({"_id": ObjectId(app.id), "status": "draft"}, {"$set": {
        "status": "submitted", "submitted_at": now, "submitted_version": 1, "updated_at": now}})
    if not res.modified_count:
        raise err(409, "already_submitted", "Your application is already submitted")
    app = Application.from_mongo(await db.applications.find_one({"_id": ObjectId(app.id)}))
    try:
        await write_version(app.id, 1, await snapshot(app, await db.users.find_one({"_id": ObjectId(user.id)})),
                            "submission", user.email)
    except DuplicateKeyError:
        pass
    await audit(request, user, "application.submitted", "application", app.id,
                after={"application_ref": app.application_ref, "version": 1})
    return await app_out(app, user)


async def render_pdf(app_id: str) -> tuple[bytes, str]:
    v = await db.application_versions.find_one({"application_id": app_id}, sort=[("version", -1)])
    if not v:
        raise err(409, "not_submitted", "PDF is available after submission")
    snap = v["snapshot"]
    imgs = {}
    for kind in ("photo", "signature"):
        f = await db.files.find_one({"_id": ObjectId(snap[f"{kind}_file_id"])}) if snap.get(f"{kind}_file_id") else None
        try:
            imgs[kind] = (await storage.get_object(f["storage_path"]))[0] if f else None
        except Exception:
            imgs[kind] = None
    app = await db.applications.find_one({"_id": ObjectId(app_id)})
    pdf = pdf_service.application_pdf(snap, v["version"], app["submitted_at"], imgs["photo"], imgs["signature"])
    return pdf, f"{snap['application_ref']}-v{v['version']}.pdf"


@router.get("/candidate/application/pdf")
async def my_pdf(user: User = Depends(require_verified_candidate)):
    app = await get_or_create(user)
    data, name = await render_pdf(app.id)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


async def submitted_app(user: User) -> Application:
    app = await get_or_create(user)
    if app.status != "submitted":
        raise err(409, "not_submitted", "Available after you submit your application")
    return app


async def set_post(app: Application, key: str, value: Any, request: Request, user: User, before: Any = None):
    await db.applications.update_one({"_id": ObjectId(app.id)}, {"$set": {f"post.{key}": value, "updated_at": now_utc()}})
    await audit(request, user, f"application.post.{key}", "application", app.id,
                before={key: before} if before is not None else None, after={key: value})


class DeclarationIn(BaseModel):
    accept: bool


@router.post("/candidate/application/post/declaration")
async def accept_declaration(body: DeclarationIn, request: Request, user: User = Depends(require_verified_candidate)):
    app = await submitted_app(user)
    if not body.accept:
        raise err(422, "not_accepted", "You must accept the declaration")
    if app.post.get("declaration"):
        raise err(409, "already_accepted", "Declaration already accepted")
    await set_post(app, "declaration", {"version": DECLARATION_PGDM["version"], "accepted_at": now_utc()}, request, user)
    return await app_out(Application.from_mongo(await db.applications.find_one({"_id": ObjectId(app.id)})), user)


@router.post("/candidate/application/post/preferences")
async def reset_preferences(body: Preferences, request: Request, user: User = Depends(require_verified_candidate)):
    app = await submitted_app(user)
    c = await active_cycle()
    if _today().isoformat() > (c.part_b_open or c.application_close):
        raise err(409, "window_closed", "The preference reset window has closed")
    clean, errors = await validate_section("preferences", body.model_dump(), app.cycle_id)
    if errors:
        raise err(422, "invalid", errors[0]["message"], errors=errors)
    old = app.sections.get("preferences", {}).get("ranked", [])
    if old == clean["ranked"]:
        raise err(409, "unchanged", "Preferences are unchanged")
    history = app.post.get("preference_history") or [{"version": 1, "ranked": old, "at": app.submitted_at}]
    history.append({"version": len(history) + 1, "ranked": clean["ranked"], "at": now_utc()})
    await db.applications.update_one({"_id": ObjectId(app.id)}, {"$set": {
        "sections.preferences": clean, "post.preference_history": history, "updated_at": now_utc()}})
    await audit(request, user, "application.preferences_reset", "application", app.id,
                before={"ranked": old}, after={"ranked": clean["ranked"]})
    return await app_out(Application.from_mongo(await db.applications.find_one({"_id": ObjectId(app.id)})), user)


class AnswersIn(BaseModel):
    answers: dict[str, str]
    submit: bool = False


def _words(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


@router.put("/candidate/application/post/{kind}")
async def save_answers(kind: str, body: AnswersIn, request: Request, user: User = Depends(require_verified_candidate)):
    if kind not in ("essays", "piq"):
        raise err(404, "unknown", "Unknown module")
    app = await submitted_app(user)
    cur = app.post.get(kind) or {}
    if cur.get("submitted_at"):
        raise err(409, "already_submitted", "Already submitted")
    spec = ESSAYS if kind == "essays" else PIQ
    answers = {q["id"]: (body.answers.get(q["id"]) or "")[:5000] for q in spec}
    if body.submit:
        errors = []
        for q in spec:
            n = _words(answers[q["id"]])
            lo, hi = (q["min_words"], q["max_words"]) if kind == "essays" else (5, 200)
            if not lo <= n <= hi:
                errors.append({"field": q["id"], "message": f"Write {lo}-{hi} words (currently {n})"})
        if errors:
            raise err(422, "invalid", "Some answers need attention", errors=errors)
    value = {"answers": answers, "saved_at": now_utc(), "submitted_at": now_utc() if body.submit else None}
    if body.submit:
        await set_post(app, kind, value, request, user)
    else:
        await db.applications.update_one({"_id": ObjectId(app.id)}, {"$set": {f"post.{kind}": value}})
    return await app_out(Application.from_mongo(await db.applications.find_one({"_id": ObjectId(app.id)})), user)


@router.post("/candidate/application/post/graduation")
async def graduation(body: dict, request: Request, user: User = Depends(require_verified_candidate)):
    app = await submitted_app(user)
    if app.post.get("graduation"):
        raise err(409, "already_submitted", "Graduation eligibility already declared")
    try:
        clean = GraduationEligibility(**body).model_dump()
    except ValidationError as e:
        errors = validation_errors(e)
        raise err(422, "invalid", errors[0]["message"], errors=errors)
    await set_post(app, "graduation", {**clean, "version": GRAD_DECL_VERSION, "submitted_at": now_utc()}, request, user)
    return await app_out(Application.from_mongo(await db.applications.find_one({"_id": ObjectId(app.id)})), user)


@router.post("/candidate/application/post/confirm")
async def confirm(request: Request, user: User = Depends(require_verified_candidate)):
    app = await submitted_app(user)
    if app.post.get("confirmation", {}) and app.post["confirmation"].get("version") == app.submitted_version:
        raise err(409, "already_confirmed", "You have already confirmed this version")
    await set_post(app, "confirmation", {"version": app.submitted_version, "confirmed_at": now_utc()}, request, user)
    return await app_out(Application.from_mongo(await db.applications.find_one({"_id": ObjectId(app.id)})), user)
