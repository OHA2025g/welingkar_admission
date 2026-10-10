from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core import BaseDocument, db, now_utc
from routes.application import Application
from routes.config import oid
from routes.interviews import Session, get_session, lookups, session_out, today_ist
from routes.policies import active_policy
from security import User, audit, err, require
from services import pdf_service
from services.xlsx import xlsx_response

router = APIRouter(prefix="/api", tags=["assessments"])


class Assessment(BaseDocument):
    cycle_id: str
    session_id: str
    type: str
    application_id: str
    candidate_id: str
    panelist_id: str
    panelist_name: str
    scores: dict[str, int] = {}
    total: float = 0
    max_total: int = 0
    normalized: float = 0
    rubric_version: int
    status: str = "draft"
    version: int = 1
    submitted_at: Optional[datetime] = None
    corrections: list[dict] = []
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


async def rubric(type: str) -> tuple[int, list[dict]]:
    v, r = await active_policy("selection_rules")
    return v, r["ga_rubric" if type == "GA" else "pi_rubric"]


def check_scores(scores: dict, rub: list[dict], full: bool) -> tuple[float, int]:
    keys = {c["key"]: c for c in rub}
    for k, v in scores.items():
        if k not in keys:
            raise err(422, "unknown_criterion", f"Unknown rubric item '{k}'")
        if not isinstance(v, int) or not 0 <= v <= keys[k]["max"]:
            raise err(422, "out_of_range", f"{keys[k]['label']} must be between 0 and {keys[k]['max']}")
    if full and set(scores) != set(keys):
        missing = [keys[k]["label"] for k in keys if k not in scores]
        raise err(422, "incomplete", f"Score every rubric item before submitting (missing: {', '.join(missing)})")
    return float(sum(scores.values())), sum(c["max"] for c in rub)


async def assigned_session(sid: str, request: Request, user: User) -> Session:
    s = await get_session(sid)
    if user.id not in s.panelist_ids:
        await audit(request, user, "access.denied", "interview_session", sid, after={"reason": "not assigned"}, outcome="denied")
        raise err(403, "not_assigned", "You are not assigned to this session")
    return s


@router.get("/panel/sessions")
async def my_sessions(user: User = Depends(require("assessments.score"))):
    locs, rooms, _ = await lookups()
    out = []
    async for raw in db.interview_sessions.find({"panelist_ids": user.id}).sort([("date", 1), ("start", 1)]):
        s = Session.from_mongo(raw)
        mine = await db.assessments.count_documents({"session_id": s.id, "panelist_id": user.id, "status": "submitted"})
        d = session_out(s, locs, rooms)
        d.update(submitted=mine, phase="today" if s.date == today_ist() else ("upcoming" if s.date > today_ist() else "past"))
        out.append(d)
    return out


def _summary(app: Application, progs: dict, with_piq: bool) -> dict:
    s = app.sections
    g = (s.get("education") or {}).get("graduation") or {}
    w = s.get("work") or {}
    out = {"graduation": f"{g.get('degree', '')} {g.get('discipline', '')} · {g.get('university', '')} ({g.get('score')})".strip(),
           "work": [f"{x['designation']}, {x['organization']}" for x in w.get("experiences", [])] if w.get("has_experience") else [],
           "exams": [f"{x['exam']} {x['year']}: {x.get('percentile') or x.get('score') or x['status']}" for x in (s.get("exams") or {}).get("exams", [])],
           "preferences": [progs.get(p, p) for p in (s.get("preferences") or {}).get("ranked", [])]}
    if with_piq:
        out["piq"] = (app.post.get("piq") or {}).get("answers", {})
    return out


@router.get("/panel/sessions/{sid}")
async def panel_session(sid: str, request: Request, user: User = Depends(require("assessments.score"))):
    s = await assigned_session(sid, request, user)
    v, rub = await rubric(s.type)
    locs, rooms, _ = await lookups()
    progs = {p["code"]: p["name"] async for p in db.programs.find({"cycle_id": s.cycle_id}, {"code": 1, "name": 1})}
    cands = []
    async for b in db.interview_bookings.find({"session_id": s.id, "status": "booked"}):
        app = Application.from_mongo(await db.applications.find_one({"_id": ObjectId(b["application_id"])}))
        u = await db.users.find_one({"_id": ObjectId(b["candidate_id"])}, {"name": 1, "candidate_ref": 1})
        a = Assessment.from_mongo(await db.assessments.find_one({"session_id": s.id, "application_id": app.id, "panelist_id": user.id}))
        cands.append({"application_id": app.id, "application_ref": app.application_ref, "name": u["name"],
                      "candidate_ref": u.get("candidate_ref"), "photo_file_id": app.photo_file_id, "attendance": b.get("attendance"),
                      "summary": _summary(app, progs, s.type == "PI"),
                      "assessment": a.model_dump(include={"id", "scores", "total", "max_total", "status", "version", "submitted_at"}) if a else None})
    return {"session": session_out(s, locs, rooms), "rubric": rub, "rubric_version": v,
            "can_score": s.date <= today_ist(), "candidates": sorted(cands, key=lambda x: x["name"])}


class ScoreEntry(BaseModel):
    application_id: str
    scores: dict[str, int]


class ScoresIn(BaseModel):
    entries: list[ScoreEntry] = Field(min_length=1)
    submit: bool = False


@router.put("/panel/sessions/{sid}/scores")
async def save_scores(sid: str, body: ScoresIn, request: Request, user: User = Depends(require("assessments.score"))):
    s = await assigned_session(sid, request, user)
    if s.date > today_ist():
        raise err(409, "session_not_started", "Scores can be entered on the session date")
    v, rub = await rubric(s.type)
    booked = {b["application_id"]: b async for b in db.interview_bookings.find({"session_id": s.id, "status": "booked"})}
    prepared = []
    for e in body.entries:
        b = booked.get(e.application_id)
        if not b:
            raise err(422, "not_in_session", "A candidate in this request is not part of your session")
        if b.get("attendance") == "absent":
            raise err(422, "absent", "Candidates marked absent cannot be scored")
        existing = await db.assessments.find_one({"session_id": s.id, "application_id": e.application_id, "panelist_id": user.id})
        if existing and existing["status"] == "submitted":
            raise err(409, "locked", "Scores already submitted are locked. Ask an administrator for an audited correction.")
        total, mx = check_scores(e.scores, rub, body.submit)
        prepared.append((e, b, total, mx))
    now = now_utc()
    for e, b, total, mx in prepared:
        doc = {"scores": e.scores, "total": total, "max_total": mx, "normalized": round(100 * total / mx, 2), "rubric_version": v,
               "status": "submitted" if body.submit else "draft", "submitted_at": now if body.submit else None, "updated_at": now}
        base = Assessment(cycle_id=s.cycle_id, session_id=s.id, type=s.type, application_id=e.application_id, candidate_id=b["candidate_id"],
                          panelist_id=user.id, panelist_name=user.name, rubric_version=v).to_mongo()
        try:
            await db.assessments.update_one(
                {"session_id": s.id, "application_id": e.application_id, "panelist_id": user.id, "status": "draft"},
                {"$set": doc, "$setOnInsert": {k: base[k] for k in ("cycle_id", "type", "candidate_id", "panelist_name", "version",
                                                                      "corrections", "created_at")}}, upsert=True)
        except DuplicateKeyError:
            raise err(409, "locked", "Scores already submitted are locked. Ask an administrator for an audited correction.")
    if body.submit:
        await audit(request, user, "assessment.submitted", "interview_session", s.id,
                    after={"type": s.type, "entries": [{"application_id": e.application_id, "scores": e.scores} for e, *_ in prepared]})
    return await panel_session(sid, request, user)


class CorrectionIn(BaseModel):
    scores: dict[str, int]
    reason: str = Field(min_length=5, max_length=500)


@router.post("/admin/assessments/{aid}/correct")
async def correct_assessment(aid: str, body: CorrectionIn, request: Request, user: User = Depends(require("assessments.correct"))):
    a = Assessment.from_mongo(await db.assessments.find_one({"_id": oid(aid)}))
    if not a:
        raise err(404, "not_found", "Assessment not found")
    if a.status != "submitted":
        raise err(409, "not_submitted", "Only submitted scores can be corrected")
    _, rub = await rubric(a.type)
    total, mx = check_scores(body.scores, rub, True)
    if body.scores == a.scores:
        raise err(409, "unchanged", "No changes to save")
    entry = {"from_version": a.version, "to_version": a.version + 1, "before": a.scores, "after": body.scores,
             "reason": body.reason, "by": user.email, "at": now_utc()}
    res = await db.assessments.update_one({"_id": ObjectId(a.id), "version": a.version}, {
        "$set": {"scores": body.scores, "total": total, "max_total": mx, "normalized": round(100 * total / mx, 2),
                 "version": a.version + 1, "updated_at": now_utc()}, "$push": {"corrections": entry}})
    if not res.modified_count:
        raise err(409, "stale_version", "Scores changed meanwhile. Reload and try again.")
    await audit(request, user, "assessment.corrected", "assessment", a.id, before=a.scores, after=body.scores,
                reason=f"v{a.version}->v{a.version + 1}: {body.reason}")
    return Assessment.from_mongo(await db.assessments.find_one({"_id": ObjectId(a.id)})).model_dump()


async def evaluation_rows(type: str, date: Optional[str], panelist_id: Optional[str], session_id: Optional[str]) -> list[dict]:
    q = {"type": type, **({"panelist_id": panelist_id} if panelist_id else {}), **({"session_id": session_id} if session_id else {})}
    locs, rooms, _ = await lookups()
    sessions = {str(s["_id"]): s async for s in db.interview_sessions.find({"type": type, **({"date": date} if date else {})})}
    rows = []
    async for raw in db.assessments.find({**q, "session_id": {"$in": list(sessions)} if not session_id else session_id}):
        a = Assessment.from_mongo(raw)
        s = sessions.get(a.session_id)
        if not s:
            continue
        u = await db.users.find_one({"_id": ObjectId(a.candidate_id)}, {"name": 1, "candidate_ref": 1})
        app = await db.applications.find_one({"_id": ObjectId(a.application_id)}, {"application_ref": 1})
        rows.append({**a.model_dump(exclude={"corrections"}), "corrections": len(a.corrections), "candidate_name": u["name"],
                     "candidate_ref": u.get("candidate_ref"), "application_ref": app["application_ref"], "date": s["date"],
                     "slot": f"{s['start']}-{s['end']}", "location": locs.get(s["location_id"], {}).get("name"),
                     "room": rooms.get(s["room_id"], {}).get("name")})
    return sorted(rows, key=lambda r: (r["date"], r["slot"], r["candidate_name"], r["panelist_name"]))


@router.get("/reports/evaluation")
async def evaluation_report(type: str = "GA", date: Optional[str] = None, panelist_id: Optional[str] = None,
                            session_id: Optional[str] = None, _: User = Depends(require("evaluations.read"))):
    v, rub = await rubric(type)
    rows = await evaluation_rows(type, date, panelist_id, session_id)
    panelists = [{"id": str(u["_id"]), "name": u["name"]} async for u in db.users.find({"role": "panelist"}).sort("name", 1)]
    return {"type": type, "rubric": rub, "rubric_version": v, "rows": rows, "panelists": panelists}


@router.get("/reports/evaluation/export")
async def evaluation_export(request: Request, type: str = "GA", date: Optional[str] = None, panelist_id: Optional[str] = None,
                            user: User = Depends(require("evaluations.read"))):
    _, rub = await rubric(type)
    rows = await evaluation_rows(type, date, panelist_id, None)
    head = ["Date", "Slot", "Location", "Room", "Panelist", "Candidate ID", "Application ref", "Candidate"] + \
           [c["label"] for c in rub] + ["Total", "Max", "Score %", "Status", "Score version", "Corrections"]
    data = [[r["date"], r["slot"], r["location"], r["room"], r["panelist_name"], r["candidate_ref"], r["application_ref"],
             r["candidate_name"]] + [r["scores"].get(c["key"], "") for c in rub] +
            [r["total"], r["max_total"], r["normalized"], r["status"], r["version"], r["corrections"]] for r in rows]
    slug = ""
    if panelist_id:
        p = await db.users.find_one({"_id": oid(panelist_id)}, {"name": 1})
        slug = "-" + "".join(ch for ch in (p["name"] if p else "panelist").lower().replace(" ", "-") if ch.isalnum() or ch == "-")
    await audit(request, user, "evaluation.exported", "export", None, after={"type": type, "panelist_id": panelist_id, "rows": len(rows)})
    return xlsx_response([(f"{type} scores", head, data)], f"weschool-{type.lower()}-scores{slug}-{now_utc():%Y%m%d-%H%M}.xlsx")


@router.get("/reports/evaluation/ga-batch/{sid}/pdf")
async def ga_batch_pdf(sid: str, _: User = Depends(require("evaluations.read"))):
    s = await get_session(sid)
    if s.type != "GA":
        raise err(422, "not_ga", "Batch reports are for GA sessions")
    _, rub = await rubric("GA")
    locs, rooms, staff = await lookups()
    rows = await evaluation_rows("GA", None, None, s.id)
    data = pdf_service.ga_batch_pdf(session_out(s, locs, rooms, staff), rub, rows)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="ga-batch-{s.date}-{s.start.replace(":", "")}.pdf"'})
