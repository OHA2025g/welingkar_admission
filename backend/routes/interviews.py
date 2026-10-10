from datetime import date as Date, datetime, timedelta
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core import BaseDocument, IST, db, now_utc
from routes.application import Application, active_cycle
from routes.config import oid
from routes.policies import active_policy
from security import User, audit, err, require, require_any, require_verified_candidate
from services import pdf_service
from services.xlsx import xlsx_response

router = APIRouter(prefix="/api", tags=["interviews"])
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
TYPE_LABEL = {"GA": "Group Assessment (GA)", "PI": "Personal Interview (PI)"}
STAGE = {"GA": "ga", "PI": "pi"}


class Location(BaseDocument):
    cycle_id: str
    name: str
    city: str
    address: str = ""
    created_at: datetime = Field(default_factory=now_utc)


class Room(BaseDocument):
    location_id: str
    name: str
    capacity: int
    created_at: datetime = Field(default_factory=now_utc)


class Session(BaseDocument):
    cycle_id: str
    type: Literal["GA", "PI"]
    location_id: str
    room_id: str
    date: str
    start: str
    end: str
    capacity: int
    booked: int = 0
    panelist_ids: list[str] = []
    panelist_attendance: dict[str, dict] = {}
    status: str = "scheduled"
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=now_utc)

    def start_dt(self) -> datetime:
        return datetime.fromisoformat(f"{self.date}T{self.start}").replace(tzinfo=IST)


class Booking(BaseDocument):
    cycle_id: str
    application_id: str
    candidate_id: str
    type: Literal["GA", "PI"]
    session_id: str
    status: str = "booked"
    source: str
    version: int = 1
    reschedules: int = 0
    history: list[dict] = []
    attendance: Optional[str] = None
    attendance_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


def today_ist() -> str:
    return datetime.now(IST).date().isoformat()


def overlaps(a: dict, b: dict) -> bool:
    return a["date"] == b["date"] and a["start"] < b["end"] and b["start"] < a["end"]


async def reserve(sid: str) -> Optional[dict]:
    return await db.interview_sessions.find_one_and_update(
        {"_id": ObjectId(sid), "status": "scheduled", "$expr": {"$lt": ["$booked", "$capacity"]}},
        {"$inc": {"booked": 1}}, return_document=ReturnDocument.AFTER)


async def release(sid: str):
    await db.interview_sessions.update_one({"_id": ObjectId(sid), "booked": {"$gt": 0}}, {"$inc": {"booked": -1}})


async def get_session(sid: str) -> Session:
    s = Session.from_mongo(await db.interview_sessions.find_one({"_id": oid(sid)}))
    if not s:
        raise err(404, "not_found", "Session not found")
    return s


async def lookups() -> tuple[dict, dict, dict]:
    locs = {str(x["_id"]): x async for x in db.interview_locations.find()}
    rooms = {str(x["_id"]): x async for x in db.interview_rooms.find()}
    staff = {str(x["_id"]): x["name"] async for x in db.users.find({"role": "panelist"}, {"name": 1})}
    return locs, rooms, staff


def session_out(s: Session, locs: dict, rooms: dict, staff: Optional[dict] = None) -> dict:
    loc, room = locs.get(s.location_id, {}), rooms.get(s.room_id, {})
    d = s.model_dump(exclude={"panelist_attendance"} if staff is None else set())
    d.update(location=loc.get("name"), city=loc.get("city"), address=loc.get("address"), room=room.get("name"),
             available=max(0, s.capacity - s.booked), type_label=TYPE_LABEL[s.type])
    if staff is not None:
        d["panelists"] = [{"id": p, "name": staff.get(p, "?"), "attendance": (s.panelist_attendance.get(p) or {}).get("status")}
                          for p in s.panelist_ids]
    else:
        d.pop("panelist_ids", None)
    return d


async def check_panelists(ids: list[str], slot: dict, exclude: Optional[str] = None) -> list[str]:
    ids = list(dict.fromkeys(ids))
    for pid in ids:
        u = await db.users.find_one({"_id": oid(pid), "role": "panelist", "status": "active"})
        if not u:
            raise err(422, "invalid_panelist", "Choose active GA/PI panelists only")
        q = {"panelist_ids": pid, "date": slot["date"], "status": "scheduled"}
        if exclude:
            q["_id"] = {"$ne": ObjectId(exclude)}
        async for other in db.interview_sessions.find(q):
            if overlaps(slot, other):
                raise err(409, "panelist_clash", f"{u['name']} is already assigned to an overlapping session "
                                                 f"({other['type']} {other['start']}-{other['end']})")
    return ids


# ---------- coordinator ----------
class LocationIn(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    city: str = Field(min_length=2, max_length=40)
    address: str = Field("", max_length=200)


class RoomIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    capacity: int = Field(ge=1, le=200)


class SessionIn(BaseModel):
    type: Literal["GA", "PI"]
    room_id: str
    date: Date
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)
    capacity: int = Field(ge=1, le=200)
    panelist_ids: list[str] = []

    @model_validator(mode="after")
    def order(self):
        if self.end <= self.start:
            raise ValueError("End time must be after start time")
        return self


class PanelistsIn(BaseModel):
    panelist_ids: list[str]


class AllocateIn(BaseModel):
    type: Literal["GA", "PI"]
    location_id: Optional[str] = None


class AttendanceIn(BaseModel):
    candidates: dict[str, Literal["present", "absent"]] = {}
    panelists: dict[str, Literal["present", "absent"]] = {}


@router.get("/interviews/locations")
async def list_locations(_: User = Depends(require("interviews.manage"))):
    c = await active_cycle()
    out = []
    async for loc in db.interview_locations.find({"cycle_id": c.id}).sort("name", 1):
        rooms = [Room.from_mongo(r).model_dump() async for r in db.interview_rooms.find({"location_id": str(loc["_id"])}).sort("name", 1)]
        out.append({**Location.from_mongo(loc).model_dump(), "rooms": rooms})
    return out


@router.post("/interviews/locations")
async def create_location(body: LocationIn, request: Request, user: User = Depends(require("interviews.manage"))):
    c = await active_cycle()
    loc = Location(cycle_id=c.id, **body.model_dump())
    loc.id = str((await db.interview_locations.insert_one(loc.to_mongo())).inserted_id)
    await audit(request, user, "interview.location_created", "interview_location", loc.id, after=body.model_dump())
    return loc.model_dump()


@router.post("/interviews/locations/{loc_id}/rooms")
async def create_room(loc_id: str, body: RoomIn, request: Request, user: User = Depends(require("interviews.manage"))):
    if not await db.interview_locations.find_one({"_id": oid(loc_id)}):
        raise err(404, "not_found", "Location not found")
    if await db.interview_rooms.find_one({"location_id": loc_id, "name": body.name}):
        raise err(409, "duplicate", "A room with this name already exists at this location")
    room = Room(location_id=loc_id, **body.model_dump())
    room.id = str((await db.interview_rooms.insert_one(room.to_mongo())).inserted_id)
    await audit(request, user, "interview.room_created", "interview_room", room.id, after=body.model_dump())
    return room.model_dump()


@router.get("/interviews/panelists")
async def list_panelists(_: User = Depends(require("interviews.manage"))):
    return [{"id": str(u["_id"]), "name": u["name"], "email": u["email"]}
            async for u in db.users.find({"role": "panelist", "status": "active"}).sort("name", 1)]


@router.get("/interviews/sessions")
async def list_sessions(type: Optional[str] = None, date: Optional[str] = None, _: User = Depends(require("interviews.manage"))):
    c = await active_cycle()
    q = {"cycle_id": c.id, **({"type": type} if type else {}), **({"date": date} if date else {})}
    locs, rooms, staff = await lookups()
    return [session_out(Session.from_mongo(s), locs, rooms, staff)
            async for s in db.interview_sessions.find(q).sort([("date", 1), ("start", 1)])]


@router.post("/interviews/sessions")
async def create_session(body: SessionIn, request: Request, user: User = Depends(require("interviews.manage"))):
    c = await active_cycle()
    room = await db.interview_rooms.find_one({"_id": oid(body.room_id)})
    if not room:
        raise err(404, "not_found", "Room not found")
    if body.capacity > room["capacity"]:
        raise err(422, "over_capacity", f"Session capacity cannot exceed the room capacity ({room['capacity']})")
    if body.date.isoformat() < today_ist():
        raise err(422, "past_date", "Sessions cannot be scheduled in the past")
    slot = {"date": body.date.isoformat(), "start": body.start, "end": body.end}
    async for other in db.interview_sessions.find({"room_id": body.room_id, "date": slot["date"], "status": "scheduled"}):
        if overlaps(slot, other):
            raise err(409, "room_clash", f"{room['name']} is already booked {other['start']}-{other['end']} on this date")
    pids = await check_panelists(body.panelist_ids, slot)
    s = Session(cycle_id=c.id, type=body.type, location_id=room["location_id"], room_id=body.room_id, capacity=body.capacity,
                panelist_ids=pids, created_by=user.email, **slot)
    s.id = str((await db.interview_sessions.insert_one(s.to_mongo())).inserted_id)
    await audit(request, user, "interview.session_created", "interview_session", s.id, after=s.model_dump(exclude={"id"}))
    locs, rooms, staff = await lookups()
    return session_out(s, locs, rooms, staff)


@router.put("/interviews/sessions/{sid}/panelists")
async def assign_panelists(sid: str, body: PanelistsIn, request: Request, user: User = Depends(require("interviews.manage"))):
    s = await get_session(sid)
    pids = await check_panelists(body.panelist_ids, s.model_dump(), exclude=s.id)
    await db.interview_sessions.update_one({"_id": ObjectId(s.id)}, {"$set": {"panelist_ids": pids}})
    await audit(request, user, "interview.panelists_assigned", "interview_session", s.id,
                before={"panelist_ids": s.panelist_ids}, after={"panelist_ids": pids})
    return await session_detail(sid, user)


@router.get("/interviews/sessions/{sid}")
async def session_detail(sid: str, _: User = Depends(require("interviews.manage"))):
    s = await get_session(sid)
    locs, rooms, staff = await lookups()
    out = []
    async for b in db.interview_bookings.find({"session_id": s.id, "status": "booked"}):
        u = await db.users.find_one({"_id": ObjectId(b["candidate_id"])})
        a = await db.applications.find_one({"_id": ObjectId(b["application_id"])}, {"application_ref": 1})
        out.append({"booking_id": str(b["_id"]), "candidate_ref": u.get("candidate_ref"), "name": u["name"], "city": u.get("city"),
                    "application_ref": a["application_ref"], "source": b["source"], "version": b["version"],
                    "attendance": b.get("attendance")})
    return {**session_out(s, locs, rooms, staff), "candidates": sorted(out, key=lambda x: x["name"])}


async def eligible_apps(kind: str) -> list[tuple[Application, dict]]:
    c = await active_cycle()
    stages = {p["code"]: p["stages"] async for p in db.programs.find({"cycle_id": c.id})}
    out = []
    async for a in db.applications.find({"cycle_id": c.id, "status": "submitted"}).sort("submitted_at", 1):
        app = Application.from_mongo(a)
        prefs = (app.sections.get("preferences") or {}).get("ranked", [])
        if any(STAGE[kind] in stages.get(p, []) for p in prefs):
            out.append((app, await db.users.find_one({"_id": ObjectId(app.candidate_id)})))
    return out


@router.post("/interviews/allocate")
async def allocate(body: AllocateIn, request: Request, user: User = Depends(require("interviews.manage"))):
    c = await active_cycle()
    q = {"cycle_id": c.id, "type": body.type, "status": "scheduled", "date": {"$gt": today_ist()}}
    if body.location_id:
        q["location_id"] = body.location_id
    sessions = [s async for s in db.interview_sessions.find(q).sort([("date", 1), ("start", 1)])]
    cities = {str(x["_id"]): x["city"] async for x in db.interview_locations.find()}
    taken = set(await db.interview_bookings.distinct("application_id", {"type": body.type, "status": "booked"}))
    allocated, unallocated = [], []
    for app, u in await eligible_apps(body.type):
        if app.id in taken:
            continue
        ordered = sorted(sessions, key=lambda s: cities.get(s["location_id"]) != u.get("city"))
        placed = None
        for s in ordered:
            if s["booked"] >= s["capacity"]:
                continue
            fresh = await reserve(str(s["_id"]))
            if not fresh:
                s["booked"] = s["capacity"]
                continue
            s["booked"] = fresh["booked"]
            b = Booking(cycle_id=c.id, application_id=app.id, candidate_id=app.candidate_id, type=body.type,
                        session_id=str(s["_id"]), source="allocation",
                        history=[{"action": "allocated", "session_id": str(s["_id"]), "at": now_utc(), "by": user.email}])
            try:
                await db.interview_bookings.insert_one(b.to_mongo())
            except DuplicateKeyError:
                await release(str(s["_id"]))
                break
            placed = s
            break
        (allocated if placed else unallocated).append(
            {"application_ref": app.application_ref, "name": u["name"],
             **({"session": f"{placed['date']} {placed['start']}"} if placed else {})})
    await audit(request, user, "interview.allocated", "interview_allocation", body.type,
                after={"type": body.type, "location_id": body.location_id, "allocated": len(allocated), "unallocated": len(unallocated)})
    return {"type": body.type, "allocated": allocated, "unallocated": unallocated}


@router.post("/interviews/sessions/{sid}/attendance")
async def mark_attendance(sid: str, body: AttendanceIn, request: Request, user: User = Depends(require("interviews.manage"))):
    s = await get_session(sid)
    if s.date > today_ist():
        raise err(409, "not_started", "Attendance can be recorded on or after the session date")
    now = now_utc()
    for bid, status in body.candidates.items():
        res = await db.interview_bookings.update_one({"_id": oid(bid), "session_id": s.id, "status": "booked"},
                                                     {"$set": {"attendance": status, "attendance_at": now}})
        if not res.matched_count:
            raise err(422, "not_in_session", "A candidate is not booked into this session")
    for pid, status in body.panelists.items():
        if pid not in s.panelist_ids:
            raise err(422, "not_assigned", "A panelist is not assigned to this session")
        await db.interview_sessions.update_one({"_id": ObjectId(s.id)}, {"$set": {
            f"panelist_attendance.{pid}": {"status": status, "at": now, "by": user.email}}})
    await audit(request, user, "interview.attendance_recorded", "interview_session", s.id, after=body.model_dump())
    return await session_detail(sid, user)


async def slot_report_data(type: Optional[str], location_id: Optional[str], date: Optional[str]) -> dict:
    c = await active_cycle()
    q = {"cycle_id": c.id, **({"type": type} if type else {}), **({"location_id": location_id} if location_id else {}),
         **({"date": date} if date else {})}
    locs, rooms, staff = await lookups()
    sessions, by_id = [], {}
    async for raw in db.interview_sessions.find(q).sort([("date", 1), ("start", 1)]):
        s = Session.from_mongo(raw)
        att = [b.get("attendance") async for b in db.interview_bookings.find({"session_id": s.id, "status": "booked"}, {"attendance": 1})]
        row = {**session_out(s, locs, rooms, staff), "present": att.count("present"), "absent": att.count("absent")}
        sessions.append(row)
        by_id[s.id] = row
    bookings = []
    async for b in db.interview_bookings.find({"session_id": {"$in": list(by_id)}, "status": "booked"}):
        u = await db.users.find_one({"_id": ObjectId(b["candidate_id"])}, {"name": 1, "candidate_ref": 1})
        s = by_id[b["session_id"]]
        hist = [f"{h['action']} {h.get('from_slot', '')}{' -> ' if h.get('from_slot') else ''}{h.get('slot', '')} ({h['by']})".strip()
                for h in b.get("history", [])]
        bookings.append({"candidate_ref": u.get("candidate_ref"), "name": u["name"], "type": b["type"],
                         "slot": f"{s['date']} {s['start']}-{s['end']}", "location": s["location"], "room": s["room"],
                         "version": b["version"], "reschedules": b["reschedules"], "source": b["source"],
                         "attendance": b.get("attendance"), "history": hist})
    panelists = [{"date": s["date"], "slot": f"{s['start']}-{s['end']}", "type": s["type"], "location": s["location"],
                  "room": s["room"], "panelist": p["name"], "attendance": p["attendance"] or "not recorded"}
                 for s in sessions for p in s["panelists"]]
    return {"sessions": sessions, "bookings": sorted(bookings, key=lambda x: (x["slot"], x["name"])), "panelists": panelists}


@router.get("/interviews/reports/slots")
async def slot_report(type: Optional[str] = None, location_id: Optional[str] = None, date: Optional[str] = None,
                      _: User = Depends(require_any("interviews.manage", "evaluations.read"))):
    return await slot_report_data(type, location_id, date)


@router.get("/interviews/reports/slots/export")
async def slot_report_export(request: Request, type: Optional[str] = None, location_id: Optional[str] = None,
                             date: Optional[str] = None, user: User = Depends(require_any("interviews.manage", "evaluations.read"))):
    d = await slot_report_data(type, location_id, date)
    await audit(request, user, "interview.slot_report_exported", "export", None, after={"type": type, "date": date})
    return xlsx_response([
        ("Sessions", ["Date", "Start", "End", "Type", "Location", "Room", "Capacity", "Booked", "Available", "Present", "Absent", "Panelists"],
         [[s["date"], s["start"], s["end"], s["type"], s["location"], s["room"], s["capacity"], s["booked"], s["available"],
           s["present"], s["absent"], ", ".join(p["name"] for p in s["panelists"])] for s in d["sessions"]]),
        ("Bookings & reschedules", ["Candidate ID", "Name", "Type", "Current slot", "Location", "Room", "Booking version",
                                    "Reschedules", "Source", "Attendance", "History"],
         [[b["candidate_ref"], b["name"], b["type"], b["slot"], b["location"], b["room"], b["version"], b["reschedules"],
           b["source"], b["attendance"] or "", " | ".join(b["history"])] for b in d["bookings"]]),
        ("Panelist attendance", ["Date", "Slot", "Type", "Location", "Room", "Panelist", "Attendance"],
         [[p["date"], p["slot"], p["type"], p["location"], p["room"], p["panelist"], p["attendance"]] for p in d["panelists"]]),
    ], f"weschool-slot-report-{now_utc():%Y%m%d-%H%M}.xlsx")


# ---------- candidate ----------
class SlotIn(BaseModel):
    session_id: str


async def pi_context(user: User) -> tuple[Optional[Application], list[str]]:
    app = Application.from_mongo(await db.applications.find_one({"candidate_id": user.id}))
    reasons = []
    if not app or app.status != "submitted":
        reasons.append("Submit your application first")
    else:
        if not (app.post.get("piq") or {}).get("submitted_at"):
            reasons.append("Complete the Personal Interview Questionnaire (PIQ) before booking a PI slot")
        progs = {p["code"]: p["stages"] async for p in db.programs.find({"cycle_id": app.cycle_id})}
        if not any("pi" in progs.get(p, []) for p in (app.sections.get("preferences") or {}).get("ranked", [])):
            reasons.append("None of your preferred programmes include a Personal Interview")
    return app, reasons


async def interview_rules() -> dict:
    _, r = await active_policy("selection_rules")
    return {"cutoff_hours": r["pi_booking_cutoff_hours"], "reschedule_limit": r["pi_reschedule_limit"]}


def bookable(s: Session, cutoff_hours: int) -> bool:
    return s.status == "scheduled" and s.start_dt() - timedelta(hours=cutoff_hours) > now_utc()


async def booking_out(b: dict, locs: dict, rooms: dict) -> dict:
    s = Session.from_mongo(await db.interview_sessions.find_one({"_id": ObjectId(b["session_id"])}))
    bk = Booking.from_mongo(b).model_dump(exclude={"history"})
    bk["session"] = session_out(s, locs, rooms)
    bk["history"] = [{k: v for k, v in h.items() if k != "by"} for h in b.get("history", [])]
    return bk


@router.get("/candidate/interviews")
async def my_interviews(user: User = Depends(require_verified_candidate)):
    app, reasons = await pi_context(user)
    rules = await interview_rules()
    locs, rooms, _ = await lookups()
    bookings = [await booking_out(b, locs, rooms) async for b in db.interview_bookings.find(
        {"application_id": app.id, "status": "booked"})] if app else []
    slots = []
    if app and not reasons:
        async for raw in db.interview_sessions.find({"cycle_id": app.cycle_id, "type": "PI", "status": "scheduled",
                                                     "date": {"$gte": today_ist()}}).sort([("date", 1), ("start", 1)]):
            s = Session.from_mongo(raw)
            slots.append({**session_out(s, locs, rooms), "bookable": bookable(s, rules["cutoff_hours"]) and s.booked < s.capacity})
    return {"eligible": not reasons, "reasons": reasons, "rules": rules, "bookings": bookings, "pi_slots": slots,
            "application_ref": app.application_ref if app else None}


async def _pi_target(sid: str, cutoff: int) -> Session:
    s = await get_session(sid)
    if s.type != "PI":
        raise err(422, "not_pi", "Choose a Personal Interview slot")
    if not bookable(s, cutoff):
        raise err(409, "booking_closed", f"Booking for this slot closed {cutoff} hours before it starts")
    return s


@router.post("/candidate/interviews/pi/book")
async def book_pi(body: SlotIn, request: Request, user: User = Depends(require_verified_candidate)):
    app, reasons = await pi_context(user)
    if reasons:
        raise err(409, "not_eligible", reasons[0])
    rules = await interview_rules()
    s = await _pi_target(body.session_id, rules["cutoff_hours"])
    if await db.interview_bookings.find_one({"application_id": app.id, "type": "PI", "status": "booked"}):
        raise err(409, "already_booked", "You already have a PI slot. Use reschedule to change it.")
    if not await reserve(s.id):
        raise err(409, "slot_full", "This slot has just filled up. Please choose another slot.")
    slot = f"{s.date} {s.start}"
    b = Booking(cycle_id=app.cycle_id, application_id=app.id, candidate_id=user.id, type="PI", session_id=s.id, source="candidate",
                history=[{"action": "booked", "session_id": s.id, "slot": slot, "version": 1, "at": now_utc(), "by": user.email}])
    try:
        b.id = str((await db.interview_bookings.insert_one(b.to_mongo())).inserted_id)
    except DuplicateKeyError:
        await release(s.id)
        raise err(409, "already_booked", "You already have a PI slot. Use reschedule to change it.")
    await audit(request, user, "interview.pi_booked", "interview_booking", b.id, after={"session_id": s.id, "slot": slot})
    return await my_interviews(user)


@router.post("/candidate/interviews/pi/reschedule")
async def reschedule_pi(body: SlotIn, request: Request, user: User = Depends(require_verified_candidate)):
    app, reasons = await pi_context(user)
    if reasons:
        raise err(409, "not_eligible", reasons[0])
    rules = await interview_rules()
    b = Booking.from_mongo(await db.interview_bookings.find_one({"application_id": app.id, "type": "PI", "status": "booked"}))
    if not b:
        raise err(409, "no_booking", "Book a PI slot first")
    if b.reschedules >= rules["reschedule_limit"]:
        raise err(409, "reschedule_limit", f"You can reschedule at most {rules['reschedule_limit']} times")
    old = await get_session(b.session_id)
    if not bookable(old, rules["cutoff_hours"]):
        raise err(409, "reschedule_closed", f"Rescheduling closes {rules['cutoff_hours']} hours before your current slot")
    if body.session_id == b.session_id:
        raise err(409, "same_slot", "You are already booked into this slot")
    new = await _pi_target(body.session_id, rules["cutoff_hours"])
    if not await reserve(new.id):
        raise err(409, "slot_full", "This slot has just filled up. Your current booking is unchanged.")
    entry = {"action": "rescheduled", "session_id": new.id, "from_slot": f"{old.date} {old.start}", "slot": f"{new.date} {new.start}",
             "version": b.version + 1, "at": now_utc(), "by": user.email}
    res = await db.interview_bookings.update_one(
        {"_id": ObjectId(b.id), "version": b.version, "status": "booked"},
        {"$set": {"session_id": new.id, "version": b.version + 1, "updated_at": now_utc(), "attendance": None},
         "$inc": {"reschedules": 1}, "$push": {"history": entry}})
    if not res.modified_count:
        await release(new.id)
        raise err(409, "stale_booking", "Your booking changed meanwhile. Reload and try again.")
    await release(old.id)
    await audit(request, user, "interview.pi_rescheduled", "interview_booking", b.id,
                before={"session_id": old.id, "version": b.version}, after={"session_id": new.id, "version": b.version + 1})
    return await my_interviews(user)


@router.get("/candidate/interviews/hall-ticket")
async def hall_ticket(user: User = Depends(require_verified_candidate)):
    app, _ = await pi_context(user)
    pi = await db.interview_bookings.find_one({"application_id": app.id, "type": "PI", "status": "booked"}) if app else None
    if not pi:
        raise err(409, "no_booking", "The hall ticket is available once you have an active PI booking")
    locs, rooms, _ = await lookups()
    items = [await booking_out(b, locs, rooms) async for b in db.interview_bookings.find(
        {"application_id": app.id, "status": "booked"}).sort("type", 1)]
    ticket = f"HT-{app.application_ref}-PI-v{pi['version']}"
    data = pdf_service.hall_ticket_pdf({"name": user.name, "candidate_ref": user.candidate_ref, "application_ref": app.application_ref,
                                        "photo": None}, items, ticket)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{ticket}.pdf"'})
