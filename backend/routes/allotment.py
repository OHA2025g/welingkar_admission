import asyncio
from datetime import date as Date, datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core import BaseDocument, db, now_utc
from routes.application import active_cycle
from routes.interviews import today_ist
from routes.partb import Consent, active_consent, eligibility_for
from routes.partb_docs import stage_status
from routes.policies import active_policy
from security import User, audit, err, require, require_any
from services import pdf_service
from services.notify import notify
from services.xlsx import xlsx_response

router = APIRouter(prefix="/api", tags=["allotment"])
SEAT = {"allotted", "provisional", "on_hold"}
ACTIVE = ("allotted", "provisional", "on_hold")


class Batch(BaseDocument):
    cycle_id: str
    kind: Literal["merit", "waitlist"]
    name: str
    program_code: str
    start_date: str
    end_date: str
    status: str = "active"
    created_by: str
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    def open(self) -> bool:
        return self.status == "active" and self.start_date <= today_ist() <= self.end_date


class Allotment(BaseDocument):
    cycle_id: str
    candidate_id: str
    application_ref: str
    program_code: str
    batch_id: str
    batch_kind: str
    status: str
    seat_held: bool
    version: int = 1
    receipt_version: int = 0
    betterment_of: Optional[str] = None
    superseded_by: Optional[str] = None
    remarks: Optional[str] = None
    history: list[dict] = []
    created_by: str
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


async def programs() -> dict:
    c = await active_cycle()
    return {p["code"]: p async for p in db.programs.find({"cycle_id": c.id})}


async def ensure_seat(cycle_id: str, code: str, capacity: int):
    await db.partb_seats.update_one({"cycle_id": cycle_id, "program_code": code},
                                    {"$setOnInsert": {"capacity": capacity, "filled": 0}}, upsert=True)


async def reserve_seat(cycle_id: str, code: str, reason: str) -> bool:
    ok = await db.partb_seats.find_one_and_update({"cycle_id": cycle_id, "program_code": code, "$expr": {"$lt": ["$filled", "$capacity"]}},
                                                  {"$inc": {"filled": 1}}, return_document=ReturnDocument.AFTER)
    if ok:
        await db.seat_events.insert_one({"program_code": code, "delta": 1, "reason": reason, "allotment_id": None, "at": now_utc()})
    return bool(ok)


async def release_seat(cycle_id: str, code: str, allotment_id: Optional[str], reason: str):
    await db.partb_seats.update_one({"cycle_id": cycle_id, "program_code": code, "filled": {"$gt": 0}}, {"$inc": {"filled": -1}})
    await db.seat_events.insert_one({"program_code": code, "delta": -1, "reason": reason, "allotment_id": allotment_id, "at": now_utc()})


async def vacancy() -> list[dict]:
    c = await active_cycle()
    progs = await programs()
    existing = {s["program_code"] async for s in db.partb_seats.find({"cycle_id": c.id}, {"program_code": 1})}
    for code, p in progs.items():
        if code not in existing:
            await ensure_seat(c.id, code, p["seat_capacity"])
    held_by = {}
    async for g in db.partb_allotments.aggregate([
        {"$match": {"cycle_id": c.id, "seat_held": True}},
        {"$group": {"_id": "$program_code", "n": {"$sum": 1}}},
    ]):
        held_by[g["_id"]] = g["n"]
    out = []
    async for s in db.partb_seats.find({"cycle_id": c.id}).sort("program_code", 1):
        held = held_by.get(s["program_code"], 0)
        vac = s["capacity"] - s["filled"]
        pct = vac / s["capacity"] if s["capacity"] else 0
        out.append({"program_code": s["program_code"], "program_name": progs.get(s["program_code"], {}).get("name"), "capacity": s["capacity"],
                    "filled": s["filled"], "vacant": vac, "reconciled": held == s["filled"], "seat_holding_allotments": held,
                    "tone": "red" if vac <= 0 else ("amber" if pct < 0.25 else "green")})
    return out


async def held_seat(cid: str) -> Optional[Allotment]:
    return Allotment.from_mongo(await db.partb_allotments.find_one({"candidate_id": cid, "seat_held": True}))


async def betterment_consent(cid: str, bid: str) -> Optional[Consent]:
    return Consent.from_mongo(await db.partb_consents.find_one({"candidate_id": cid, "kind": "betterment", "batch_id": bid}))


async def betterment_offers(cid: str) -> list[dict]:
    cur = await held_seat(cid)
    if not cur:
        return []
    rows = await eligibility_for(cid)
    cur_choice = next((e.choice_position for e in rows if e.program_code == cur.program_code), None) or 99
    progs, out = await programs(), []
    for e in rows:
        if e.outcome != "waitlisted" or e.program_code == cur.program_code or (e.choice_position or 99) >= cur_choice:
            continue
        async for b in db.partb_batches.find({"kind": "waitlist", "program_code": e.program_code, "status": "active"}):
            bt = Batch.from_mongo(b)
            if bt.start_date > today_ist():
                continue
            cons = await betterment_consent(cid, bt.id)
            state = cons.courses[e.program_code] if cons else ("expired" if bt.end_date < today_ist() else "pending")
            out.append({"batch_id": bt.id, "batch_name": bt.name, "program_code": e.program_code, "program_name": progs[e.program_code]["name"],
                        "waitlist_rank": e.waitlist_rank, "end_date": bt.end_date, "response": state, "current_program": cur.program_code})
    return out


# ---------- batches ----------
class BatchIn(BaseModel):
    kind: Literal["merit", "waitlist"]
    name: str = Field(min_length=3, max_length=80)
    program_code: str
    start_date: Date
    end_date: Date

    @model_validator(mode="after")
    def dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date")
        return self


class BatchPatch(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    start_date: Date
    end_date: Date
    version_hint: Optional[str] = None

    @model_validator(mode="after")
    def dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date")
        return self


async def get_batch(bid: str) -> Batch:
    b = Batch.from_mongo(await db.partb_batches.find_one({"_id": ObjectId(bid), "status": "active"})) if ObjectId.is_valid(bid) else None
    if not b:
        raise err(404, "not_found", "Batch not found")
    return b


@router.get("/partb/batches")
async def list_batches(kind: Optional[str] = None, _: User = Depends(require("partb.read"))):
    c = await active_cycle()
    progs = await programs()
    out = []
    async for b in db.partb_batches.find({"cycle_id": c.id, "status": "active", **({"kind": kind} if kind else {})}).sort([("program_code", 1), ("start_date", 1)]):
        bt = Batch.from_mongo(b)
        n = await db.partb_allotments.count_documents({"batch_id": bt.id, "status": {"$in": list(ACTIVE)}})
        out.append({**bt.model_dump(), "program_name": progs.get(bt.program_code, {}).get("name"), "open": bt.open(), "active_allotments": n})
    return out


@router.post("/partb/batches")
async def create_batch(body: BatchIn, request: Request, user: User = Depends(require("partb.manage"))):
    c = await active_cycle()
    if body.program_code not in await programs():
        raise err(422, "unknown_program", "Unknown program")
    b = Batch(cycle_id=c.id, kind=body.kind, name=body.name, program_code=body.program_code, start_date=body.start_date.isoformat(),
              end_date=body.end_date.isoformat(), created_by=user.email)
    b.id = str((await db.partb_batches.insert_one(b.to_mongo())).inserted_id)
    await audit(request, user, "partb.batch_created", "partb_batch", b.id, after=b.model_dump(exclude={"id"}))
    return b.model_dump()


@router.put("/partb/batches/{bid}")
async def update_batch(bid: str, body: BatchPatch, request: Request, user: User = Depends(require("partb.manage"))):
    b = await get_batch(bid)
    patch = {"name": body.name, "start_date": body.start_date.isoformat(), "end_date": body.end_date.isoformat(), "updated_at": now_utc()}
    await db.partb_batches.update_one({"_id": ObjectId(b.id)}, {"$set": patch})
    await audit(request, user, "partb.batch_updated", "partb_batch", b.id, before=b.model_dump(include={"name", "start_date", "end_date"}),
                after={k: patch[k] for k in ("name", "start_date", "end_date")})
    return (await get_batch(bid)).model_dump()


@router.delete("/partb/batches/{bid}")
async def delete_batch(bid: str, request: Request, user: User = Depends(require("partb.manage"))):
    b = await get_batch(bid)
    if await db.partb_allotments.find_one({"batch_id": b.id, "status": {"$ne": "rejected"}}):
        raise err(409, "has_allotments", "This batch has committed allotments and cannot be deleted")
    res = await db.partb_batches.update_one({"_id": ObjectId(b.id), "status": "active"}, {"$set": {"status": "deleted", "updated_at": now_utc()}})
    if not res.modified_count:
        raise err(409, "stale", "Batch already deleted")
    await audit(request, user, "partb.batch_deleted", "partb_batch", b.id, before=b.model_dump(exclude={"id"}))
    return {"deleted": b.id}


@router.get("/partb/batches/{bid}/dashboard")
async def batch_dashboard(bid: str, _: User = Depends(require("partb.read"))):
    b = await get_batch(bid)
    want = "selected" if b.kind == "merit" else "waitlisted"
    key = "merit_rank" if b.kind == "merit" else "waitlist_rank"
    rows = []
    async for e in db.partb_eligibility.find({"program_code": b.program_code, "outcome": want, "status": "active"}).sort(key, 1):
        cid = e["candidate_id"]
        u = await db.users.find_one({"_id": ObjectId(cid)}, {"name": 1, "candidate_ref": 1})
        cons = await active_consent(cid)
        mine = await db.partb_allotments.find_one({"candidate_id": cid, "batch_id": b.id}, sort=[("created_at", -1)])
        held = await held_seat(cid)
        better = await betterment_consent(cid, b.id) if held and held.program_code != b.program_code else None
        rows.append({"candidate_id": cid, "name": u["name"], "candidate_ref": u.get("candidate_ref"), "application_ref": e["application_ref"],
                     "rank": e[key], "choice": e.get("choice_position"),
                     "consent": (cons.courses.get(b.program_code) if cons else None) or "pending",
                     "docs": (await stage_status(cid, "initial"))["status"],
                     "status": mine["status"] if mine else "awaiting", "allotment_id": str(mine["_id"]) if mine else None,
                     "allotment_version": mine["version"] if mine else None,
                     "holds_seat_in": held.program_code if held and held.program_code != b.program_code else None,
                     "betterment_consent": better.courses.get(b.program_code) if better else None})
    counts = {s: sum(r["status"] == s for r in rows) for s in ("awaiting", "allotted", "provisional", "on_hold", "rejected", "cancelled", "superseded")}
    vac = next((v for v in await vacancy() if v["program_code"] == b.program_code), None)
    return {"batch": {**b.model_dump(), "open": b.open()}, "rows": rows, "counts": counts, "vacancy": vac}


class AllotIn(BaseModel):
    candidate_id: str
    status: Literal["allotted", "provisional", "on_hold"] = "allotted"
    remarks: str = Field("", max_length=300)


def _hist(action: str, user: User, **kw) -> dict:
    return {"action": action, "by": user.email, "at": now_utc(), **kw}


@router.post("/partb/batches/{bid}/allot")
async def allot(bid: str, body: AllotIn, request: Request, user: User = Depends(require("partb.manage"))):
    b = await get_batch(bid)
    if not b.open():
        raise err(409, "batch_closed", f"Batch is open {b.start_date} to {b.end_date}")
    cid, code = body.candidate_id, b.program_code
    want = "selected" if b.kind == "merit" else "waitlisted"
    elig = next((e for e in await eligibility_for(cid) if e.program_code == code and e.outcome == want), None)
    if not elig:
        raise err(422, "not_eligible", f"Candidate is not {want} for {code}")
    cons = await active_consent(cid)
    if not cons or not cons.overall or cons.courses.get(code) != "accept":
        raise err(409, "no_consent", "Candidate has not consented to this course")
    docs = (await stage_status(cid, "initial"))["status"]
    if docs in ("not_started", "incomplete"):
        raise err(409, "docs_incomplete", "Candidate has not uploaded all required documents")
    if body.status == "allotted" and docs != "verified":
        raise err(409, "docs_not_verified", "Documents must be verified for a final allotment (use provisional or on hold)")
    cur = await held_seat(cid)
    if cur and cur.program_code == code:
        raise err(409, "already_allotted", "Candidate already holds a seat in this course")
    if cur:
        bc = await betterment_consent(cid, b.id)
        if not bc or bc.courses.get(code) != "accept":
            raise err(409, "betterment_consent_required", f"Candidate holds a seat in {cur.program_code}; fresh betterment consent is required")
    _, rules = await active_policy("admission_rules")
    if body.status == "on_hold" and not rules["on_hold_consumes_seat"]:
        if cur:
            raise err(409, "hold_needs_seat", "Policy: on-hold does not reserve a seat, so it cannot be used for betterment")
        a = Allotment(cycle_id=b.cycle_id, candidate_id=cid, application_ref=elig.application_ref, program_code=code, batch_id=b.id,
                      batch_kind=b.kind, status="on_hold", seat_held=False, remarks=body.remarks or None, created_by=user.email,
                      history=[_hist("on_hold", user, batch=b.name, version=1, seat_reserved=False)])
        a.id = str((await db.partb_allotments.insert_one(a.to_mongo())).inserted_id)
        await audit(request, user, "partb.allotted", "partb_allotment", a.id, after={"program_code": code, "status": "on_hold", "seat_held": False})
        return a.model_dump()
    if not await reserve_seat(b.cycle_id, code, f"reserve for {elig.application_ref}"):
        raise err(409, "no_seat", f"No vacant seat left in {code}")
    new = Allotment(cycle_id=b.cycle_id, candidate_id=cid, application_ref=elig.application_ref, program_code=code, batch_id=b.id,
                    batch_kind=b.kind, status=body.status, seat_held=True, receipt_version=1 if body.status != "on_hold" else 0,
                    betterment_of=cur.id if cur else None, remarks=body.remarks or None, created_by=user.email,
                    history=[_hist(body.status, user, batch=b.name, version=1)])
    new.id = str(ObjectId())
    if cur:
        res = await db.partb_allotments.update_one({"_id": ObjectId(cur.id), "seat_held": True, "version": cur.version}, {
            "$set": {"seat_held": False, "status": "superseded", "superseded_by": new.id, "version": cur.version + 1, "updated_at": now_utc()},
            "$push": {"history": _hist("superseded", user, by_allotment=new.id, version=cur.version + 1)}})
        if not res.modified_count:
            await release_seat(b.cycle_id, code, None, "rollback: betterment conflict")
            raise err(409, "stale", "The candidate's allotment changed meanwhile. Reload and try again.")
    try:
        await db.partb_allotments.insert_one(new.to_mongo())
    except DuplicateKeyError:
        await release_seat(b.cycle_id, code, None, "rollback: candidate already holds a seat")
        if cur:
            await db.partb_allotments.update_one({"_id": ObjectId(cur.id), "superseded_by": new.id}, {
                "$set": {"seat_held": True, "status": cur.status, "superseded_by": None, "version": cur.version + 2},
                "$push": {"history": _hist("restored", user, version=cur.version + 2)}})
        raise err(409, "already_allotted", "Candidate was allotted a seat by another request")
    await db.seat_events.update_one({"program_code": code, "allotment_id": None, "delta": 1, "reason": f"reserve for {elig.application_ref}"},
                                    {"$set": {"allotment_id": new.id}})
    if cur:
        await release_seat(cur.cycle_id, cur.program_code, cur.id, f"betterment: superseded by {new.id}")
    await audit(request, user, "partb.allotted", "partb_allotment", new.id,
                before=cur.model_dump(include={"program_code", "status"}) if cur else None,
                after={"program_code": code, "status": body.status, "batch": b.name})
    progs = await programs()
    await notify(cid, "allotment", f"Seat {body.status.replace('_', ' ')}: {progs[code]['name']}",
                 f"You have a seat ({body.status.replace('_', ' ')}) in {progs[code]['name']} via {b.name}."
                 + (f" Your earlier seat in {progs[cur.program_code]['name']} is released." if cur else ""), email=True)
    return Allotment.from_mongo(await db.partb_allotments.find_one({"_id": ObjectId(new.id)})).model_dump()


class RejectIn(BaseModel):
    candidate_id: str
    remarks: str = Field(min_length=5, max_length=300)


@router.post("/partb/batches/{bid}/reject")
async def reject(bid: str, body: RejectIn, request: Request, user: User = Depends(require("partb.manage"))):
    b = await get_batch(bid)
    if await db.partb_allotments.find_one({"candidate_id": body.candidate_id, "batch_id": b.id, "seat_held": True}):
        raise err(409, "has_seat", "Candidate holds a seat from this batch; cancel it instead")
    elig = next((e for e in await eligibility_for(body.candidate_id) if e.program_code == b.program_code), None)
    if not elig:
        raise err(422, "not_eligible", "Candidate is not in this batch")
    a = Allotment(cycle_id=b.cycle_id, candidate_id=body.candidate_id, application_ref=elig.application_ref, program_code=b.program_code,
                  batch_id=b.id, batch_kind=b.kind, status="rejected", seat_held=False, remarks=body.remarks, created_by=user.email,
                  history=[_hist("rejected", user, remarks=body.remarks)])
    a.id = str((await db.partb_allotments.insert_one(a.to_mongo())).inserted_id)
    await audit(request, user, "partb.allotment_rejected", "partb_allotment", a.id, after={"program_code": b.program_code}, reason=body.remarks)
    return a.model_dump()


async def _end_seat(a: Allotment, to: str, request: Request, user: User, reason: str):
    res = await db.partb_allotments.update_one({"_id": ObjectId(a.id), "seat_held": True, "version": a.version}, {
        "$set": {"status": to, "seat_held": False, "version": a.version + 1, "remarks": reason, "updated_at": now_utc()},
        "$push": {"history": _hist(to, user, remarks=reason, version=a.version + 1)}})
    if not res.modified_count:
        raise err(409, "stale", "Allotment changed meanwhile. Reload and try again.")
    await release_seat(a.cycle_id, a.program_code, a.id, f"{to}: {reason}")
    await audit(request, user, f"partb.allotment_{to}", "partb_allotment", a.id, before={"status": a.status}, after={"status": to}, reason=reason)
    await notify(a.candidate_id, "allotment", "Your seat was cancelled", f"Your seat in {a.program_code} was cancelled. Reason: {reason}", email=True)


class DispositionIn(BaseModel):
    to: Literal["allotted", "provisional", "cancelled"]
    remarks: str = Field(min_length=3, max_length=300)


@router.post("/partb/allotments/{aid}/disposition")
async def disposition(aid: str, body: DispositionIn, request: Request, user: User = Depends(require("partb.manage"))):
    a = Allotment.from_mongo(await db.partb_allotments.find_one({"_id": ObjectId(aid)})) if ObjectId.is_valid(aid) else None
    if not a:
        raise err(404, "not_found", "Allotment not found")
    if a.status != "on_hold":
        raise err(409, "not_on_hold", "Only on-hold allotments can be disposed")
    if body.to == "cancelled" and a.seat_held:
        await _end_seat(a, "cancelled", request, user, body.remarks)
    elif body.to == "cancelled":
        res = await db.partb_allotments.update_one({"_id": ObjectId(a.id), "status": "on_hold", "version": a.version}, {
            "$set": {"status": "cancelled", "version": a.version + 1, "remarks": body.remarks, "updated_at": now_utc()},
            "$push": {"history": _hist("cancelled", user, remarks=body.remarks, version=a.version + 1)}})
        if not res.modified_count:
            raise err(409, "stale", "Allotment changed meanwhile. Reload and try again.")
        await audit(request, user, "partb.allotment_cancelled", "partb_allotment", a.id, before={"status": "on_hold"}, after={"status": "cancelled"})
    else:
        if body.to == "allotted" and (await stage_status(a.candidate_id, "initial"))["status"] != "verified":
            raise err(409, "docs_not_verified", "Documents must be verified for a final allotment")
        reserved = False
        if not a.seat_held:
            if not await reserve_seat(a.cycle_id, a.program_code, f"hold→{body.to} {a.application_ref}"):
                raise err(409, "no_seat", f"No vacant seat left in {a.program_code}")
            reserved = True
        try:
            res = await db.partb_allotments.update_one({"_id": ObjectId(a.id), "status": "on_hold", "version": a.version}, {
                "$set": {"status": body.to, "seat_held": True, "version": a.version + 1, "receipt_version": a.receipt_version + 1,
                         "remarks": body.remarks, "updated_at": now_utc()},
                "$push": {"history": _hist(body.to, user, remarks=body.remarks, version=a.version + 1)}})
        except DuplicateKeyError:
            res = None
        if not res or not res.modified_count:
            if reserved:
                await release_seat(a.cycle_id, a.program_code, None, "rollback: disposition conflict")
            raise err(409, "stale", "Allotment changed meanwhile or candidate already holds a seat. Reload and try again.")
        await audit(request, user, "partb.allotment_disposed", "partb_allotment", a.id, before={"status": "on_hold"}, after={"status": body.to},
                    reason=body.remarks)
        await notify(a.candidate_id, "allotment", f"Seat confirmed ({body.to})", f"Your on-hold seat in {a.program_code} is now {body.to}.", email=True)
    return Allotment.from_mongo(await db.partb_allotments.find_one({"_id": ObjectId(a.id)})).model_dump()


class CancelIn(BaseModel):
    application_ref: str
    reason: str = Field(min_length=5, max_length=300)


@router.post("/partb/allotments/cancel")
async def cancel_by_roll(body: CancelIn, request: Request, user: User = Depends(require("partb.manage"))):
    app = await db.applications.find_one({"application_ref": body.application_ref.strip()})
    a = await held_seat(app["candidate_id"]) if app else None
    if not a:
        raise err(404, "no_allotment", "No active allotment for this application reference")
    await _end_seat(a, "cancelled", request, user, body.reason)
    return Allotment.from_mongo(await db.partb_allotments.find_one({"_id": ObjectId(a.id)})).model_dump()


@router.get("/partb/allotments")
async def list_allotments(status: Optional[str] = None, _: User = Depends(require("partb.read"))):
    c = await active_cycle()
    out = []
    async for a in db.partb_allotments.find({"cycle_id": c.id, **({"status": status} if status else {})}).sort("created_at", -1):
        u = await db.users.find_one({"_id": ObjectId(a["candidate_id"])}, {"name": 1, "candidate_ref": 1})
        out.append({**Allotment.from_mongo(a).model_dump(exclude={"history"}), "name": u["name"], "candidate_ref": u.get("candidate_ref")})
    return out


@router.get("/partb/vacancy")
async def get_vacancy(_: User = Depends(require_any("partb.read", "partb.manage"))):
    return await vacancy()


class SeatIn(BaseModel):
    capacity: int = Field(ge=0, le=5000)


@router.put("/partb/seats/{code}")
async def set_capacity(code: str, body: SeatIn, request: Request, user: User = Depends(require("seats.manage"))):
    c = await active_cycle()
    p = (await programs()).get(code)
    if not p:
        raise err(404, "not_found", "Unknown program")
    if body.capacity > p["seat_capacity"]:
        raise err(422, "over_approved", f"Part B capacity cannot exceed the approved intake ({p['seat_capacity']})")
    await ensure_seat(c.id, code, p["seat_capacity"])
    before = await db.partb_seats.find_one({"cycle_id": c.id, "program_code": code})
    res = await db.partb_seats.update_one({"cycle_id": c.id, "program_code": code, "filled": {"$lte": body.capacity}}, {"$set": {"capacity": body.capacity}})
    if not res.matched_count:
        raise err(409, "below_filled", "Capacity cannot be lower than seats already filled")
    await audit(request, user, "partb.seat_capacity_set", "partb_seat", code, before={"capacity": before["capacity"]}, after={"capacity": body.capacity})
    return next(v for v in await vacancy() if v["program_code"] == code)


# ---------- candidate ----------
@router.get("/candidate/partb")
async def my_partb(user: User = Depends(require("self.application"))):
    rows = await eligibility_for(user.id)
    if not any(e.outcome in ("selected", "waitlisted") for e in rows):
        return {"eligible": False, "reason": "Part B opens only for candidates selected or waitlisted in the published merit list."}
    progs = await programs()
    app = await db.applications.find_one({"candidate_id": user.id}, {"application_ref": 1, "sections.personal.category": 1})
    cur = await held_seat(user.id)
    last = cur or Allotment.from_mongo(await db.partb_allotments.find_one({"candidate_id": user.id, "status": {"$ne": "rejected"}},
                                                                          sort=[("created_at", -1)]))
    cons = await active_consent(user.id)
    unread = await db.notifications.count_documents({"user_id": user.id, "read_at": None})
    return {"eligible": True, "profile": {"name": user.name, "candidate_ref": user.candidate_ref, "application_ref": app["application_ref"],
                                          "category": app.get("sections", {}).get("personal", {}).get("category")},
            "courses": [{**e.model_dump(include={"program_code", "outcome", "merit_rank", "waitlist_rank", "choice_position"}),
                         "program_name": progs[e.program_code]["name"]} for e in rows],
            "consent": cons.model_dump() if cons else None,
            "documents": {s: await stage_status(user.id, s) for s in ("initial", "admission")},
            "allotment": {**last.model_dump(exclude={"history"}), "program_name": progs[last.program_code]["name"]} if last else None,
            "betterment_offers": await betterment_offers(user.id), "unread": unread}


class BettermentIn(BaseModel):
    response: Literal["accept", "decline"]


@router.post("/candidate/partb/betterment/{bid}")
async def betterment_respond(bid: str, body: BettermentIn, request: Request, user: User = Depends(require("self.application"))):
    offer = next((o for o in await betterment_offers(user.id) if o["batch_id"] == bid), None)
    if not offer:
        raise err(404, "no_offer", "No betterment offer for this round")
    if offer["response"] != "pending":
        raise err(409, "already_responded" if offer["response"] != "expired" else "expired", f"Betterment offer is {offer['response']}")
    c = Consent(cycle_id=(await active_cycle()).id, candidate_id=user.id, kind="betterment", batch_id=bid,
                courses={offer["program_code"]: body.response}, overall=True, actor=user.email)
    try:
        c.id = str((await db.partb_consents.insert_one(c.to_mongo())).inserted_id)
    except DuplicateKeyError:
        raise err(409, "already_responded", "You already responded to this offer")
    await audit(request, user, "partb.betterment_consent", "partb_consent", c.id, after={"batch_id": bid, **c.courses})
    return await my_partb(user)


async def allotment_receipt(cid: str, name: str, cref: Optional[str]) -> tuple[bytes, str]:
    a = await held_seat(cid)
    if not a or a.status not in ("allotted", "provisional"):
        raise err(409, "no_allotment", "The allotment receipt is available after a seat is allotted")
    b = await db.partb_batches.find_one({"_id": ObjectId(a.batch_id)})
    p = (await programs())[a.program_code]
    ref = f"AR-{a.application_ref}-{a.program_code}-r{a.receipt_version}"
    return pdf_service.allotment_receipt_pdf({"name": name, "candidate_ref": cref, "application_ref": a.application_ref},
                                             {**a.model_dump(), "program_name": p["name"], "campus": p["campus"], "batch_name": b["name"],
                                              "committed_at": a.created_at}, ref), ref


@router.get("/candidate/partb/allotment/receipt")
async def receipt(user: User = Depends(require("self.application"))):
    data, ref = await allotment_receipt(user.id, user.name, user.candidate_ref)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{ref}.pdf"'})


# ---------- admin candidate list & reports ----------
async def _candidate_row(cid: str) -> dict:
    u, rows, cons, held, initial, admission = await asyncio.gather(
        db.users.find_one({"_id": ObjectId(cid)}, {"name": 1, "candidate_ref": 1}),
        eligibility_for(cid),
        active_consent(cid),
        held_seat(cid),
        stage_status(cid, "initial"),
        stage_status(cid, "admission"),
    )
    return {"candidate_id": cid, "name": u["name"], "candidate_ref": u.get("candidate_ref"), "application_ref": rows[0].application_ref,
            "courses": [e.model_dump(include={"program_code", "outcome", "merit_rank", "waitlist_rank", "choice_position"}) for e in rows],
            "consent": cons.model_dump(include={"courses", "overall", "version", "created_at", "actor"}) if cons else None,
            "docs_initial": initial["status"], "docs_admission": admission["status"],
            "allotment": held.model_dump(include={"id", "program_code", "status", "version"}) if held else None}


@router.get("/partb/candidates")
async def partb_candidates(_: User = Depends(require("partb.read"))):
    cids = await db.partb_eligibility.distinct("candidate_id", {"status": "active"})
    rows = await asyncio.gather(*(_candidate_row(cid) for cid in cids)) if cids else []
    return sorted(rows, key=lambda r: r["name"])


async def overview() -> list[dict]:
    cands, vac, counts = await asyncio.gather(partb_candidates(), vacancy(), _allotment_counts())
    out = []
    for v in vac:
        code = v["program_code"]
        rel = [c for c in cands if any(x["program_code"] == code and x["outcome"] != "rejected" for x in c["courses"])]
        out.append({**v, "eligible": len(rel), "consented": sum(1 for c in rel if c["consent"] and c["consent"]["courses"].get(code) == "accept"),
                    "docs_verified": sum(1 for c in rel if c["docs_initial"] == "verified"),
                    **{s: counts.get((code, s), 0) for s in
                       ("allotted", "provisional", "on_hold", "cancelled", "superseded", "rejected")}})
    return out


async def _allotment_counts() -> dict:
    counts = {}
    async for g in db.partb_allotments.aggregate([
        {"$group": {"_id": {"p": "$program_code", "s": "$status"}, "n": {"$sum": 1}}},
    ]):
        counts[(g["_id"]["p"], g["_id"]["s"])] = g["n"]
    return counts


@router.get("/partb/reports/overview")
async def report_overview(_: User = Depends(require("partb.read"))):
    return await overview()


@router.get("/partb/reports/export")
async def report_export(request: Request, user: User = Depends(require("partb.read"))):
    ov, cands, allots = await overview(), await partb_candidates(), await list_allotments(None, user)
    events = []
    async for a in db.partb_allotments.find():
        for h in a.get("history", []):
            events.append([h["at"].strftime("%Y-%m-%d %H:%M"), a["application_ref"], a["program_code"], h["action"], h["by"], h.get("remarks") or ""])
    await audit(request, user, "partb.report_exported", "export", None, after={"candidates": len(cands)})
    return xlsx_response([
        ("Counselling overview", ["Program", "Capacity", "Filled", "Vacant", "Eligible", "Consented", "Docs verified", "Allotted", "Provisional",
                                  "On hold", "Cancelled", "Superseded", "Rejected", "Reconciled"],
         [[o["program_code"], o["capacity"], o["filled"], o["vacant"], o["eligible"], o["consented"], o["docs_verified"], o["allotted"],
           o["provisional"], o["on_hold"], o["cancelled"], o["superseded"], o["rejected"], "yes" if o["reconciled"] else "NO"] for o in ov]),
        ("Consent detail", ["Candidate ID", "Name", "Application", "Consent version", "Overall", "Courses", "Recorded by"],
         [[c["candidate_ref"], c["name"], c["application_ref"], (c["consent"] or {}).get("version"), (c["consent"] or {}).get("overall"),
           ", ".join(f"{k}:{v}" for k, v in ((c["consent"] or {}).get("courses") or {}).items()), (c["consent"] or {}).get("actor")] for c in cands]),
        ("Current allotments", ["Candidate ID", "Name", "Application", "Program", "Batch kind", "Status", "Seat held", "Version"],
         [[a["candidate_ref"], a["name"], a["application_ref"], a["program_code"], a["batch_kind"], a["status"], a["seat_held"], a["version"]]
          for a in allots]),
        ("Day-to-day allotment", ["When (UTC)", "Application", "Program", "Event", "By", "Remarks"], sorted(events)),
        ("Documents", ["Candidate ID", "Name", "Counselling docs", "Admission docs"],
         [[c["candidate_ref"], c["name"], c["docs_initial"], c["docs_admission"]] for c in cands]),
    ], f"weschool-partb-{now_utc():%Y%m%d-%H%M}.xlsx")
