"""Detailed staff reports across admissions, seats, finance, and interviews."""
import asyncio
from collections import Counter
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, Request

from core import db, now_utc
from rbac import UNMASKED_CONTACT_ROLES
from routes.allotment import vacancy
from routes.otp import _mask
from security import User, audit, require
from services.xlsx import xlsx_response

router = APIRouter(prefix="/api", tags=["reports"])

FUNNEL = (
    ("registered", "Registered"),
    ("verified", "Verified"),
    ("partially_verified", "Partially verified"),
    ("application_fee_paid", "Application fee paid"),
    ("draft", "Draft applications"),
    ("submitted", "Submitted applications"),
)
SEAT_STATUSES = ("allotted", "provisional", "on_hold", "cancelled", "rejected")


def _bucket() -> dict:
    return {"collected_count": 0, "collected_paise": 0, "refunded_count": 0, "refunded_paise": 0}


def _programme_key(order: dict, seats: dict) -> str:
    if order.get("fee_code") == "application_fee":
        return "Application fee"
    aid = order.get("allotment_id")
    if aid and str(aid) in seats:
        return seats[str(aid)]
    desc = order.get("description") or ""
    if "·" in desc:
        return desc.split("·")[-1].strip() or "Unassigned"
    return "Unassigned"


async def build_detailed_report() -> dict:
    cycle, program_docs, users, apps, paid_ids, seat_groups, allotment_docs, orders, refunds, cancellations, session_docs, booking_docs, score_docs, results, seats_live = await asyncio.gather(
        db.cycles.find_one({"status": "active"}, {"code": 1}),
        db.programs.find({}, {"code": 1, "name": 1}).to_list(None),
        db.users.find({"role": "candidate"}, {"state": 1, "identity_status": 1}).to_list(None),
        db.applications.find({}, {"candidate_id": 1, "status": 1, "sections.preferences.ranked": 1}).to_list(None),
        db.payment_orders.distinct("candidate_id", {"fee_code": "application_fee", "status": "paid"}),
        db.partb_allotments.aggregate([
            {"$group": {"_id": {"program_code": "$program_code", "status": "$status"}, "n": {"$sum": 1}}},
        ]).to_list(None),
        db.partb_allotments.find({}, {"program_code": 1}).to_list(None),
        db.payment_orders.find({}, {"fee_code": 1, "status": 1, "amount_paise": 1, "allotment_id": 1, "description": 1}).to_list(None),
        db.refunds.find({"status": "succeeded"}, {"order_id": 1, "amount_paise": 1}).to_list(None),
        db.cancellations.find({}, {"status": 1, "program_code": 1, "quote.refund_paise": 1}).to_list(None),
        db.interview_sessions.find({}, {"type": 1}).to_list(None),
        db.interview_bookings.find({}, {"status": 1}).to_list(None),
        db.assessments.find({}, {"status": 1}).to_list(None),
        db.result_versions.find({}, {"version": 1, "status": 1}).sort("version", 1).to_list(None),
        vacancy(),
    )
    cycle = cycle or {}
    names = {p["code"]: p["name"] for p in program_docs}
    app_by_candidate = {a["candidate_id"]: a for a in apps}
    paid_app_fee = set(paid_ids)

    by_state: dict[str, dict] = {}
    for u in users:
        state = u.get("state") or "—"
        row = by_state.setdefault(state, {"state": state, "registered": 0, "verified": 0, "fee_paid": 0, "submitted": 0})
        cid = str(u["_id"])
        app = app_by_candidate.get(cid)
        row["registered"] += 1
        row["verified"] += u.get("identity_status") == "verified"
        row["fee_paid"] += cid in paid_app_fee
        row["submitted"] += bool(app and app.get("status") == "submitted")

    demand: Counter = Counter()
    for app in apps:
        ranked = ((app.get("sections") or {}).get("preferences") or {}).get("ranked") or []
        if ranked:
            demand[ranked[0]] += 1

    identity = Counter(u.get("identity_status") for u in users)
    app_status = Counter(a.get("status") for a in apps)
    funnel_counts = {
        "registered": len(users),
        "verified": identity.get("verified", 0),
        "partially_verified": identity.get("partially_verified", 0),
        "application_fee_paid": len(paid_app_fee),
        "draft": app_status.get("draft", 0),
        "submitted": app_status.get("submitted", 0),
    }

    seat_counts = {(g["_id"]["program_code"], g["_id"]["status"]): g["n"] for g in seat_groups}
    seats = []
    for v in seats_live:
        code = v["program_code"]
        seats.append({
            "program_code": code, "program_name": v.get("program_name") or names.get(code) or code,
            "capacity": v["capacity"], "filled": v["filled"], "vacant": v["vacant"], "reconciled": v["reconciled"],
            **{status: seat_counts.get((code, status), 0) for status in SEAT_STATUSES},
        })

    allotment_programmes = {str(a["_id"]): a["program_code"] for a in allotment_docs}
    finance_rows = {code: {"program_code": code, "program_name": names.get(code, code), **_bucket()} for code in sorted(names)}
    finance_rows["Application fee"] = {"program_code": "Application fee", "program_name": "Application fee", **_bucket()}
    pay_status: dict[str, dict] = {}
    for order in orders:
        status = order.get("status") or "unknown"
        slot = pay_status.setdefault(status, {"status": status, "count": 0, "amount_paise": 0})
        slot["count"] += 1
        slot["amount_paise"] += order.get("amount_paise") or 0
        if status != "paid":
            continue
        key = _programme_key(order, allotment_programmes)
        row = finance_rows.setdefault(key, {"program_code": key, "program_name": names.get(key, key), **_bucket()})
        row["collected_count"] += 1
        row["collected_paise"] += order.get("amount_paise") or 0
    refund_order_ids = [ObjectId(r["order_id"]) for r in refunds if ObjectId.is_valid(str(r.get("order_id")))]
    refund_orders = {str(o["_id"]): o async for o in db.payment_orders.find(
        {"_id": {"$in": refund_order_ids}}, {"fee_code": 1, "allotment_id": 1, "description": 1})} if refund_order_ids else {}
    for refund in refunds:
        order = refund_orders.get(str(refund.get("order_id"))) or {}
        key = _programme_key(order, allotment_programmes)
        row = finance_rows.setdefault(key, {"program_code": key, "program_name": names.get(key, key), **_bucket()})
        row["refunded_count"] += 1
        row["refunded_paise"] += refund.get("amount_paise") or 0

    cancel_status: dict[str, dict] = {}
    cancel_programmes: dict[str, dict] = {}
    for c in cancellations:
        status = c.get("status") or "unknown"
        refund_paise = int(((c.get("quote") or {}).get("refund_paise")) or 0)
        slot = cancel_status.setdefault(status, {"status": status, "count": 0, "refund_paise": 0})
        slot["count"] += 1
        slot["refund_paise"] += refund_paise
        code = c.get("program_code") or "—"
        prow = cancel_programmes.setdefault(code, {"program_code": code, "program_name": names.get(code, code), "count": 0, "refund_paise": 0})
        prow["count"] += 1
        prow["refund_paise"] += refund_paise

    sessions, bookings, scores = Counter(), Counter(), Counter()
    for s in session_docs:
        sessions[s.get("type") or "—"] += 1
    for b in booking_docs:
        bookings[b.get("status") or "—"] += 1
    for a in score_docs:
        scores[a.get("status") or "—"] += 1
    results = [{"version": v["version"], "status": v.get("status")} for v in results]

    programmes = sorted(finance_rows.values(), key=lambda r: (r["program_code"] == "Application fee", r["program_code"]))
    return {
        "generated_at": now_utc().isoformat(),
        "cycle_code": cycle.get("code"),
        "admissions": {
            "funnel": [{"key": key, "label": label, "count": funnel_counts[key]} for key, label in FUNNEL],
            "by_state": sorted(by_state.values(), key=lambda r: (-r["registered"], r["state"])),
            "first_preferences": [{"program_code": code, "program_name": names.get(code, code), "count": demand.get(code, 0)} for code in sorted(names)],
        },
        "seats": seats,
        "finance": {
            "by_programme": programmes,
            "totals": {k: sum(r[k] for r in programmes) for k in ("collected_count", "collected_paise", "refunded_count", "refunded_paise")},
            "payments_by_status": sorted(pay_status.values(), key=lambda r: r["status"]),
            "cancellations": sorted(cancel_status.values(), key=lambda r: r["status"]),
            "cancellations_by_programme": sorted(cancel_programmes.values(), key=lambda r: r["program_code"]),
        },
        "interviews": {
            "sessions": [{"type": k, "count": v} for k, v in sorted(sessions.items())],
            "bookings": [{"status": k, "count": v} for k, v in sorted(bookings.items())],
            "scores": [{"status": k, "count": v} for k, v in sorted(scores.items())],
            "results": results,
        },
    }


def _sheets(report: dict) -> list:
    adm, fin, iv = report["admissions"], report["finance"], report["interviews"]
    return [
        ("Admissions funnel", ["Step", "Count"], [[r["label"], r["count"]] for r in adm["funnel"]]),
        ("Candidates by state", ["State", "Registered", "Verified", "Fee paid", "Submitted"],
         [[r["state"], r["registered"], r["verified"], r["fee_paid"], r["submitted"]] for r in adm["by_state"]]),
        ("First preferences", ["Programme", "Name", "Count"],
         [[r["program_code"], r["program_name"], r["count"]] for r in adm["first_preferences"]]),
        ("Seats", ["Programme", "Name", "Capacity", "Filled", "Vacant", "Allotted", "Provisional", "On hold", "Cancelled", "Rejected", "Reconciled"],
         [[r["program_code"], r["program_name"], r["capacity"], r["filled"], r["vacant"], r["allotted"], r["provisional"], r["on_hold"], r["cancelled"], r["rejected"], "yes" if r["reconciled"] else "no"] for r in report["seats"]]),
        ("Collections", ["Programme", "Name", "Collected count", "Collected INR", "Refund count", "Refunded INR"],
         [[r["program_code"], r["program_name"], r["collected_count"], r["collected_paise"] / 100, r["refunded_count"], r["refunded_paise"] / 100] for r in fin["by_programme"]]),
        ("Payment status", ["Status", "Count", "Amount INR"], [[r["status"], r["count"], r["amount_paise"] / 100] for r in fin["payments_by_status"]]),
        ("Cancellations", ["Status", "Count", "Quoted refund INR"], [[r["status"], r["count"], r["refund_paise"] / 100] for r in fin["cancellations"]]),
        ("Cancellations by programme", ["Programme", "Name", "Count", "Quoted refund INR"],
         [[r["program_code"], r["program_name"], r["count"], r["refund_paise"] / 100] for r in fin["cancellations_by_programme"]]),
        ("Interviews", ["Kind", "Label", "Count"],
         [["session", r["type"], r["count"]] for r in iv["sessions"]] + [["booking", r["status"], r["count"]] for r in iv["bookings"]] + [["score", r["status"], r["count"]] for r in iv["scores"]]),
        ("Result versions", ["Version", "Status"], [[r["version"], r["status"]] for r in iv["results"]]),
    ]


def _person(user: dict, application_ref: str | None, mask: bool) -> dict:
    email = user.get("email")
    return {"name": user.get("name"), "email": _mask("email", email) if mask and email else email,
            "candidate_ref": user.get("candidate_ref"), "application_ref": application_ref, "state": user.get("state")}


@router.get("/reports/people")
async def report_people(slice: Literal["state", "programme", "cancellation"] = Query(...), key: str = Query(min_length=1),
                        user: User = Depends(require("reports.read"))):
    mask = user.role not in UNMASKED_CONTACT_ROLES
    rows = []
    if slice == "state":
        async for person in db.users.find({"role": "candidate", "state": key}).limit(50):
            app = await db.applications.find_one({"candidate_id": str(person["_id"])}, {"application_ref": 1})
            rows.append(_person(person, (app or {}).get("application_ref"), mask))
    elif slice == "programme":
        async for app in db.applications.find({"sections.preferences.ranked.0": key}).limit(50):
            person = await db.users.find_one({"_id": ObjectId(app["candidate_id"])}) if ObjectId.is_valid(app.get("candidate_id", "")) else None
            if person:
                rows.append({**_person(person, app.get("application_ref"), mask), "program_code": key})
    else:
        async for cxl in db.cancellations.find({"status": key}).limit(50):
            person = await db.users.find_one({"_id": ObjectId(cxl["candidate_id"])}) if ObjectId.is_valid(cxl.get("candidate_id", "")) else None
            if person:
                rows.append({**_person(person, cxl.get("application_ref"), mask), "program_code": cxl.get("program_code")})
    return {"rows": rows, "masked": mask, "slice": slice, "key": key}


@router.get("/reports/detailed")
async def detailed(_: User = Depends(require("reports.read"))):
    return await build_detailed_report()


@router.get("/reports/detailed/export")
async def detailed_export(request: Request, user: User = Depends(require("reports.read"))):
    report = await build_detailed_report()
    await audit(request, user, "reports.detailed_exported", "export", None, after={"cycle_code": report["cycle_code"]})
    return xlsx_response(_sheets(report), f"weschool-reports-{now_utc():%Y%m%d-%H%M}.xlsx")
