import hashlib
import json
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core import BaseDocument, db, now_utc
from routes.application import Application, active_cycle
from routes.policies import active_policy
from security import User, audit, err, require, require_candidate
from services import pdf_service
from services.xlsx import xlsx_response

router = APIRouter(prefix="/api", tags=["results"])
OUTCOME_LABEL = {"selected": "Selected", "waitlisted": "Waitlisted", "not_selected": "Not selected",
                 "incomplete": "Result pending (assessment incomplete)",
                 "manual_selection": "Institute selection (no automated shortlist)"}


class ResultVersion(BaseDocument):
    cycle_id: str
    version: int
    status: str = "generated"
    note: str = ""
    ruleset: dict
    inputs: dict
    summary: dict
    rows: list[dict] = []
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=now_utc)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    published_by: Optional[str] = None
    published_at: Optional[datetime] = None


def _avg(xs: Optional[list]) -> Optional[float]:
    return round(sum(xs) / len(xs), 2) if xs else None


def _outcome(composite: float, rank: int, seats: int, sel: float, wl: float) -> str:
    if composite >= sel and rank <= seats:
        return "selected"
    return "waitlisted" if composite >= wl else "not_selected"


async def compute(cycle_id: str) -> tuple[list[dict], dict, dict]:
    rv, rules = await active_policy("selection_rules")
    tv, tfw = await active_policy("tfw_rules")
    progs = {p["code"]: p async for p in db.programs.find({"cycle_id": cycle_id})}
    apps = [Application.from_mongo(a) async for a in db.applications.find({"cycle_id": cycle_id, "status": "submitted"})]
    users = {str(u["_id"]): u async for u in db.users.find({"_id": {"$in": [ObjectId(a.candidate_id) for a in apps]}})}
    scores: dict = {}
    n_assess = 0
    async for s in db.assessments.find({"cycle_id": cycle_id, "status": "submitted"}):
        scores.setdefault((s["application_id"], s["type"]), []).append(s["normalized"])
        n_assess += 1
    rows, fingerprint = [], []
    for a in apps:
        u = users[a.candidate_id]
        exams = (a.sections.get("exams") or {}).get("exams", [])
        exam = max([float(x["percentile"]) for x in exams if x.get("percentile") is not None] or [0.0])
        ga, pi = _avg(scores.get((a.id, "GA"))), _avg(scores.get((a.id, "PI")))
        income = (a.sections.get("family") or {}).get("annual_family_income_inr")
        tfw_income = bool(tfw.get("enabled")) and income is not None and income <= tfw["family_income_limit_inr"]
        prefs = (a.sections.get("preferences") or {}).get("ranked", [])
        fingerprint.append([a.id, a.submitted_version, exam, ga, pi, income, prefs])
        for choice, code in enumerate(prefs, 1):
            p = progs.get(code)
            if not p:
                continue
            need_ga, need_pi = "ga" in p["stages"], "pi" in p["stages"]
            row = {"candidate_id": a.candidate_id, "candidate_ref": u.get("candidate_ref"), "name": u["name"],
                   "application_ref": a.application_ref, "program_code": code, "program_name": p["name"], "route": p["route"],
                   "choice": choice, "exam_percentile": exam, "ga": ga if need_ga else None, "pi": pi if need_pi else None,
                   "composite": None, "rank": None, "outcome": None, "tfw_eligible": tfw_income and p["route"] in tfw.get("eligible_routes", []),
                   "tfw_rank": None, "tfw_outcome": None}
            if not need_ga and not need_pi:
                row["outcome"] = "manual_selection"
            elif (need_ga and ga is None) or (need_pi and pi is None):
                row["outcome"] = "incomplete"
            else:
                w = {"exam": rules["exam_weight"], "ga": rules["ga_weight"] if need_ga else 0, "pi": rules["pi_weight"] if need_pi else 0}
                row["composite"] = round((exam * w["exam"] + (ga or 0) * w["ga"] + (pi or 0) * w["pi"]) / sum(w.values()), 2)
            rows.append(row)
    sel, wl = rules["selected_cutoff"], rules["waitlist_cutoff"]
    for code, p in progs.items():
        group = sorted([r for r in rows if r["program_code"] == code and r["composite"] is not None],
                       key=lambda r: (-r["composite"], -r["exam_percentile"], r["application_ref"]))
        for rank, r in enumerate(group, 1):
            r["rank"], r["outcome"] = rank, _outcome(r["composite"], rank, p["seat_capacity"], sel, wl)
        if p.get("tfw_seats"):
            for rank, r in enumerate([r for r in group if r["tfw_eligible"]], 1):
                r["tfw_rank"], r["tfw_outcome"] = rank, _outcome(r["composite"], rank, p["tfw_seats"], sel, wl)
    rows.sort(key=lambda r: (r["program_code"], r["rank"] or 10 ** 6, r["name"]))
    inputs = {"applications": len(apps), "assessments": n_assess,
              "checksum": hashlib.sha256(json.dumps(sorted(fingerprint), default=str).encode()).hexdigest()}
    ruleset = {"selection_rules_version": rv, "selection_rules": rules, "tfw_policy_version": tv, "tfw_policy": tfw}
    return rows, inputs, ruleset


def _summary(rows: list[dict]) -> dict:
    keys = list(OUTCOME_LABEL)
    return {"rows": len(rows), "candidates": len({r["candidate_id"] for r in rows}),
            **{k: sum(r["outcome"] == k for r in rows) for k in keys},
            "tfw_selected": sum(r["tfw_outcome"] == "selected" for r in rows),
            "tfw_waitlisted": sum(r["tfw_outcome"] == "waitlisted" for r in rows)}


async def generate_version(actor_email: str, note: str) -> ResultVersion:
    c = await active_cycle()
    rows, inputs, ruleset = await compute(c.id)
    for _ in range(3):
        latest = await db.result_versions.find_one({"cycle_id": c.id}, sort=[("version", -1)])
        rv = ResultVersion(cycle_id=c.id, version=(latest["version"] + 1) if latest else 1, note=note, ruleset=ruleset,
                           inputs=inputs, summary=_summary(rows), rows=rows, created_by=actor_email)
        try:
            rv.id = str((await db.result_versions.insert_one(rv.to_mongo())).inserted_id)
            return rv
        except DuplicateKeyError:
            continue
    raise err(409, "busy", "Another generation is running. Try again.")


async def transition(version: int, frm: str, to: str, actor_email: str) -> ResultVersion:
    c = await active_cycle()
    stamp = {"approved": "approved", "published": "published"}[to]
    doc = await db.result_versions.find_one_and_update(
        {"cycle_id": c.id, "version": version, "status": frm},
        {"$set": {"status": to, f"{stamp}_by": actor_email, f"{stamp}_at": now_utc()}}, return_document=ReturnDocument.AFTER)
    if not doc:
        cur = await db.result_versions.find_one({"cycle_id": c.id, "version": version}, {"status": 1})
        if not cur:
            raise err(404, "not_found", "Result version not found")
        raise err(409, "invalid_state", f"Version {version} is '{cur['status']}'; it must be '{frm}' to become '{to}'")
    if to == "published":
        await db.result_versions.update_many({"cycle_id": c.id, "status": "published", "version": {"$ne": version}},
                                             {"$set": {"status": "superseded"}})
        await db.cycles.update_one({"_id": ObjectId(c.id)}, {"$set": {"published_result_version": version, "results_published_at": now_utc()}})
    return ResultVersion.from_mongo(doc)


class GenerateIn(BaseModel):
    note: str = Field("", max_length=300)


@router.post("/results/versions")
async def create_version(body: GenerateIn, request: Request, user: User = Depends(require("results.generate"))):
    rv = await generate_version(user.email, body.note)
    await audit(request, user, "results.generated", "result_version", f"v{rv.version}",
                after={"inputs": rv.inputs, "summary": rv.summary, "rules_version": rv.ruleset["selection_rules_version"]}, reason=body.note)
    return rv.model_dump(exclude={"rows"})


@router.get("/results/versions")
async def list_versions(_: User = Depends(require("results.read"))):
    c = await active_cycle()
    return [ResultVersion.from_mongo(v).model_dump(exclude={"rows"})
            async for v in db.result_versions.find({"cycle_id": c.id}, {"rows": 0}).sort("version", -1)]


async def _get(version: int) -> ResultVersion:
    c = await active_cycle()
    rv = ResultVersion.from_mongo(await db.result_versions.find_one({"cycle_id": c.id, "version": version}))
    if not rv:
        raise err(404, "not_found", "Result version not found")
    return rv


@router.get("/results/versions/{version}")
async def get_version(version: int, program: Optional[str] = None, _: User = Depends(require("results.read"))):
    rv = await _get(version)
    d = rv.model_dump()
    if program:
        d["rows"] = [r for r in d["rows"] if r["program_code"] == program]
    d["programs"] = sorted({(r["program_code"], r["program_name"]) for r in rv.rows})
    return d


@router.get("/results/versions/{version}/export")
async def export_version(version: int, request: Request, user: User = Depends(require("results.read"))):
    rv = await _get(version)
    head = ["Program", "Route", "Candidate ID", "Application ref", "Name", "Choice", "Exam %ile", "GA %", "PI %", "Composite", "Rank", "Outcome"]
    gen = [[r["program_name"], r["route"], r["candidate_ref"], r["application_ref"], r["name"], r["choice"], r["exam_percentile"],
            r["ga"], r["pi"], r["composite"], r["rank"], OUTCOME_LABEL[r["outcome"]]] for r in rv.rows]
    tfw = [[r["program_name"], r["route"], r["candidate_ref"], r["application_ref"], r["name"], r["choice"], r["exam_percentile"],
            r["ga"], r["pi"], r["composite"], r["tfw_rank"], OUTCOME_LABEL.get(r["tfw_outcome"], "")] for r in rv.rows if r["tfw_rank"]]
    await audit(request, user, "results.exported", "result_version", f"v{version}")
    return xlsx_response([("General merit", head, gen), ("TFW merit", head[:-2] + ["TFW rank", "TFW outcome"], tfw)],
                         f"weschool-results-v{version}-{rv.status}.xlsx")


class DecisionIn(BaseModel):
    note: str = Field("", max_length=300)


@router.post("/results/versions/{version}/approve")
async def approve(version: int, body: DecisionIn, request: Request, user: User = Depends(require("results.publish"))):
    rv = await transition(version, "generated", "approved", user.email)
    await audit(request, user, "results.approved", "result_version", f"v{version}", after={"summary": rv.summary}, reason=body.note)
    return rv.model_dump(exclude={"rows"})


@router.post("/results/versions/{version}/publish")
async def publish(version: int, body: DecisionIn, request: Request, user: User = Depends(require("results.publish"))):
    c = await active_cycle()
    prev = (await db.cycles.find_one({"_id": ObjectId(c.id)})).get("published_result_version")
    rv = await transition(version, "approved", "published", user.email)
    await audit(request, user, "results.published", "result_version", f"v{version}",
                before={"published_version": prev}, after={"published_version": version, "summary": rv.summary}, reason=body.note)
    return rv.model_dump(exclude={"rows"})


async def _my_results(user: User) -> tuple[Optional[ResultVersion], list[dict]]:
    c = await active_cycle()
    cyc = await db.cycles.find_one({"_id": ObjectId(c.id)})
    v = cyc.get("published_result_version")
    rv = ResultVersion.from_mongo(await db.result_versions.find_one({"cycle_id": c.id, "version": v, "status": "published"})) if v else None
    if not rv:
        return None, []
    return rv, [{**r, "outcome_label": OUTCOME_LABEL[r["outcome"]],
                 "tfw_outcome_label": OUTCOME_LABEL.get(r["tfw_outcome"]) if r["tfw_outcome"] else None}
                for r in rv.rows if r["candidate_id"] == user.id]


@router.get("/candidate/results")
async def my_results(user: User = Depends(require_candidate)):
    rv, rows = await _my_results(user)
    if not rv:
        return {"published": False, "rows": []}
    return {"published": True, "version": rv.version, "published_at": rv.published_at, "rows": sorted(rows, key=lambda r: r["choice"])}


@router.get("/candidate/results/pdf")
async def my_results_pdf(user: User = Depends(require_candidate)):
    rv, rows = await _my_results(user)
    if not rv:
        raise err(409, "not_published", "Results have not been published yet")
    if not rows:
        raise err(404, "no_result", "No published result for your application")
    data = pdf_service.result_pdf({"name": user.name, "candidate_ref": user.candidate_ref}, sorted(rows, key=lambda r: r["choice"]),
                                  rv.version, rv.published_at)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="WeSchool-result-{user.candidate_ref}-v{rv.version}.pdf"'})
