import asyncio
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core import db
from rbac import ROLE_PERMS
from routes.allotment import allotment_receipt, held_seat, vacancy
from routes.application import render_pdf
from routes.cancellation import Cancellation, cancellation_pdf, refresh_quote
from routes.otp import _mask
from routes.partb import active_consent, eligibility_for
from routes.partb_docs import stage_status
from security import User, audit, err, require, require_any
from services import pdf_service

router = APIRouter(prefix="/api", tags=["admin-360"])
KIND_PERMS = {"application": ("applications.read",), "allotment": ("partb.read",), "payment": ("payments.read", "partb.manage"),
              "cancellation": ("partb.read", "payments.read", "cancellations.review")}


async def _cand(cid: str) -> dict:
    u = await db.users.find_one({"_id": ObjectId(cid), "role": "candidate"}) if ObjectId.is_valid(cid) else None
    if not u:
        raise err(404, "not_found", "Candidate not found")
    return u


@router.get("/admin/candidates/search")
async def search(q: str, _: User = Depends(require_any("candidates.read", "print.center"))):
    s = q.strip()
    if len(s) < 3:
        return []
    app = await db.applications.find_one({"application_ref": s})
    filt = {"_id": ObjectId(app["candidate_id"])} if app else {"role": "candidate", "$or": [
        {"candidate_ref": s.upper()}, {"email": s.lower()}, {"name": {"$regex": s, "$options": "i"}}]}
    return [{"id": str(u["_id"]), "name": u["name"], "candidate_ref": u.get("candidate_ref")} async for u in db.users.find(filt).limit(10)]


@router.get("/admin/candidates/{cid}/360")
async def candidate_360(cid: str, request: Request, user: User = Depends(require("candidates.read"))):
    u = await _cand(cid)
    mask = user.role == "auditor"
    app = await db.applications.find_one({"candidate_id": cid}, {"sections": 0})
    pay = [{k: o.get(k) for k in ("order_ref", "fee_code", "status", "origin", "amount_paise", "refunded_paise", "paid_at")}
           async for o in db.payment_orders.find({"candidate_id": cid}).sort("created_at", 1)]
    bookings = [{k: b.get(k) for k in ("type", "status", "version", "reschedules", "attendance")} async for b in db.interview_bookings.find({"candidate_id": cid})]
    cyc = await db.cycles.find_one({"published_result_version": {"$ne": None}})
    res = await db.result_versions.find_one({"version": cyc.get("published_result_version"), "status": "published"}) if cyc else None
    results = [{k: r[k] for k in ("program_code", "outcome", "rank", "composite", "tfw_outcome")} for r in (res or {}).get("rows", []) if r["candidate_id"] == cid]
    cons = await active_consent(cid)
    seat = await held_seat(cid)
    allots = [{k: a.get(k) for k in ("program_code", "status", "batch_kind", "version", "seat_held")} async for a in db.partb_allotments.find({"candidate_id": cid})]
    cxl = []
    async for raw in db.cancellations.find({"candidate_id": cid}):
        c = Cancellation.from_mongo(raw)
        row = c.model_dump(include={"cancellation_ref", "status", "program_code", "quote", "seat_released"})
        row["quote"] = await refresh_quote(c.quote, c.candidate_id, c.id)
        cxl.append(row)
    trail = [{"at": a["at"], "action": a["action"], "actor": a.get("actor_email")} async for a in
             db.audit_logs.find({"$or": [{"actor_id": cid}, {"entity_id": cid}, {"entity_id": str(app["_id"]) if app else "-"}]}).sort("at", -1).limit(25)]
    await audit(request, user, "candidate.360_viewed", "candidate", cid)
    return {"profile": {"id": cid, "name": u["name"], "candidate_ref": u.get("candidate_ref"), "state": u.get("state"), "city": u.get("city"),
                        "email": _mask("email", u["email"]) if mask else u["email"],
                        "mobile": _mask("whatsapp", u.get("mobile") or "+0000000000") if mask else u.get("mobile"),
                        "email_verified": bool(u.get("email_verified_at")), "mobile_verified": bool(u.get("whatsapp_verified_at")), "status": u.get("identity_status")},
            "application": {k: (app or {}).get(k) for k in ("application_ref", "status", "submitted_at", "submitted_version")},
            "payments": pay, "interviews": bookings, "results": results,
            "partb": {"eligibility": [e.model_dump(include={"program_code", "outcome", "merit_rank", "waitlist_rank"}) for e in await eligibility_for(cid)],
                      "consent_version": cons.version if cons else None, "docs_initial": (await stage_status(cid, "initial"))["status"],
                      "docs_admission": (await stage_status(cid, "admission"))["status"],
                      "seat": seat.model_dump(include={"program_code", "status"}) if seat else None, "allotments": allots},
            "cancellations": cxl, "audit": trail, "masked": mask, "can_edit": "candidates.edit" in ROLE_PERMS[user.role]}


class ProfileEdit(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    city: Optional[str] = Field(None, min_length=2, max_length=60)
    state: Optional[str] = Field(None, min_length=2, max_length=60)
    reason: str = Field(min_length=5, max_length=300)


@router.patch("/admin/candidates/{cid}/profile")
async def edit_profile(cid: str, body: ProfileEdit, request: Request, user: User = Depends(require("candidates.edit"))):
    u = await _cand(cid)
    patch = {k: v.strip() for k, v in body.model_dump(exclude={"reason"}).items() if v}
    if not patch:
        raise err(422, "nothing", "Change at least one field")
    await db.users.update_one({"_id": u["_id"]}, {"$set": patch})
    await audit(request, user, "candidate.profile_corrected", "candidate", cid, before={k: u.get(k) for k in patch}, after=patch, reason=body.reason)
    return await candidate_360(cid, request, user)


@router.get("/admin/print/{kind}/{cid}")
async def print_doc(kind: Literal["application", "allotment", "payment", "cancellation"], cid: str, request: Request,
                    fee: str = "admission_fee", user: User = Depends(require("print.center"))):
    if not any(p in ROLE_PERMS[user.role] for p in KIND_PERMS[kind]):
        raise err(403, "forbidden", "You cannot print this document type")
    u = await _cand(cid)
    if kind == "application":
        app = await db.applications.find_one({"candidate_id": cid, "status": "submitted"})
        if not app:
            raise err(409, "not_submitted", "No submitted application")
        data, name = await render_pdf(str(app["_id"]))
    elif kind == "allotment":
        data, name = await allotment_receipt(cid, u["name"], u.get("candidate_ref"))
    elif kind == "payment":
        o = await db.payment_orders.find_one({"candidate_id": cid, "fee_code": fee, "status": "paid"})
        if not o:
            raise err(409, "not_paid", "No verified payment for this fee")
        data, name = pdf_service.receipt_pdf(o, await db.refunds.find({"order_id": str(o["_id"])}).to_list(50)), o["order_ref"]
    else:
        c = Cancellation.from_mongo(await db.cancellations.find_one({"candidate_id": cid, "status": {"$in": ["approved", "refunded", "closed"]}}))
        if not c:
            raise err(409, "not_approved", "No approved cancellation")
        data, name = await cancellation_pdf(c)
    await audit(request, user, "print.generated", "candidate", cid, after={"kind": kind})
    name = name if name.endswith(".pdf") else f"{name}.pdf"
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/admin/overview")
async def overview(_: User = Depends(require_any("reports.read", "partb.read", "payments.read", "applications.read"))):
    n = db.users.count_documents
    (registered, verified, drafts, submitted, sessions, booked, scored, consented, allotted, provisional, on_hold,
     offline_pending, exceptions, cancellations_pending, refunds_due, paid, vac, cyc, eligible) = await asyncio.gather(
        n({"role": "candidate"}),
        n({"role": "candidate", "identity_status": "verified"}),
        db.applications.count_documents({"status": "draft"}),
        db.applications.count_documents({"status": "submitted"}),
        db.interview_sessions.count_documents({}),
        db.interview_bookings.count_documents({"status": "booked"}),
        db.assessments.count_documents({"status": "submitted"}),
        db.partb_consents.count_documents({"kind": "initial", "status": "active"}),
        db.partb_allotments.count_documents({"status": "allotted"}),
        db.partb_allotments.count_documents({"status": "provisional"}),
        db.partb_allotments.count_documents({"status": "on_hold"}),
        db.payment_orders.count_documents({"status": "awaiting_verification"}),
        db.payment_orders.count_documents({"status": {"$in": ["amount_mismatch", "duplicate_payment"]}}),
        db.cancellations.count_documents({"status": "requested"}),
        db.cancellations.count_documents({"status": {"$in": ["approved", "refund_failed"]}}),
        db.payment_orders.find({"status": "paid"}, {"fee_code": 1, "amount_paise": 1, "refunded_paise": 1}).to_list(None),
        vacancy(),
        db.cycles.find_one({"status": "active"}),
        db.partb_eligibility.distinct("candidate_id", {"status": "active", "outcome": {"$ne": "rejected"}}),
    )
    cyc = cyc or {}
    return {
        "part_a": {"registered": registered, "verified": verified,
                   "app_fee_paid": sum(o["fee_code"] == "application_fee" for o in paid),
                   "drafts": drafts, "submitted": submitted},
        "interviews": {"sessions": sessions, "booked": booked, "scored": scored,
                       "published_version": cyc.get("published_result_version")},
        "part_b": {"eligible": len(eligible), "consented": consented, "allotted": allotted,
                   "provisional": provisional, "on_hold": on_hold,
                   "seats_capacity": sum(v["capacity"] for v in vac), "seats_filled": sum(v["filled"] for v in vac),
                   "vacancy_reconciled": all(v["reconciled"] for v in vac)},
        "finance": {"admission_paid": sum(o["fee_code"] == "admission_fee" for o in paid),
                    "collected_inr": sum(o["amount_paise"] for o in paid) / 100, "refunded_inr": sum(o.get("refunded_paise", 0) for o in paid) / 100,
                    "offline_pending": offline_pending, "exceptions": exceptions,
                    "cancellations_pending": cancellations_pending, "refunds_due": refunds_due},
    }
