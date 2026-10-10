from datetime import date, datetime
from typing import Literal, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from pymongo.errors import DuplicateKeyError

from core import BaseDocument, db, now_utc
from security import User, audit, err, require

router = APIRouter(prefix="/api", tags=["configuration"])

CycleStatus = Literal["draft", "active", "closed", "archived"]
ProgramStatus = Literal["active", "inactive"]
STAGES = ["application", "essay", "ga", "pi", "part_b"]


def oid(v: str) -> ObjectId:
    try:
        return ObjectId(v)
    except (InvalidId, TypeError):
        raise err(404, "not_found", "Not found")


class Cycle(BaseDocument):
    code: str
    name: str
    status: CycleStatus = "draft"
    application_open: str
    application_close: str
    part_b_open: Optional[str] = None
    part_b_close: Optional[str] = None
    application_fee_inr: float
    admission_fee_inr: float = 0
    admission_fee_due: Optional[str] = None
    version: int = 1
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class CycleIn(BaseModel):
    code: str = Field(min_length=4, max_length=20, pattern=r"^[A-Za-z0-9\-]+$")
    name: str = Field(min_length=3, max_length=120)
    status: CycleStatus = "draft"
    application_open: date
    application_close: date
    part_b_open: Optional[date] = None
    part_b_close: Optional[date] = None
    application_fee_inr: float = Field(ge=0, le=100000)
    admission_fee_inr: float = Field(default=0, ge=0, le=5000000)
    admission_fee_due: Optional[date] = None

    @model_validator(mode="after")
    def dates(self):
        if self.application_close < self.application_open:
            raise ValueError("Application close date cannot be before open date")
        if self.part_b_open and self.part_b_close and self.part_b_close < self.part_b_open:
            raise ValueError("Part B close date cannot be before open date")
        return self

    def store(self) -> dict:
        return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in self.model_dump().items()}


class CyclePatch(CycleIn):
    version: int


class Program(BaseDocument):
    cycle_id: str
    code: str
    name: str
    route: str
    campus: str
    duration_months: int
    seat_capacity: int
    tfw_seats: int = 0
    application_fee_inr: Optional[float] = None
    stages: list[str] = []
    status: ProgramStatus = "active"
    version: int = 1
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class ProgramIn(BaseModel):
    cycle_id: str
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Z0-9\-]+$")
    name: str = Field(min_length=3, max_length=120)
    route: str = Field(min_length=2, max_length=60)
    campus: str = Field(min_length=2, max_length=60)
    duration_months: int = Field(ge=1, le=60)
    seat_capacity: int = Field(ge=0, le=5000)
    tfw_seats: int = Field(default=0, ge=0)
    application_fee_inr: Optional[float] = Field(default=None, ge=0, le=100000)
    stages: list[str] = []
    status: ProgramStatus = "active"

    @model_validator(mode="after")
    def check(self):
        if self.tfw_seats > self.seat_capacity:
            raise ValueError("TFW seats cannot exceed seat capacity")
        bad = [s for s in self.stages if s not in STAGES]
        if bad:
            raise ValueError(f"Unknown stages: {', '.join(bad)}")
        return self


class ProgramPatch(ProgramIn):
    version: int


async def _active_conflict(cid: Optional[ObjectId]):
    q = {"status": "active"}
    if cid:
        q["_id"] = {"$ne": cid}
    other = await db.cycles.find_one(q)
    if other:
        raise err(409, "another_active", f"Cycle {other['code']} is already active. Close it first.")


@router.get("/cycles")
async def list_cycles(_: User = Depends(require("cycles.read"))):
    return [Cycle.from_mongo(d).model_dump() async for d in db.cycles.find().sort("application_open", -1)]


@router.post("/cycles")
async def create_cycle(body: CycleIn, request: Request, user: User = Depends(require("cycles.write"))):
    if body.status == "active":
        await _active_conflict(None)
    c = Cycle(**body.store())
    try:
        res = await db.cycles.insert_one(c.to_mongo())
    except DuplicateKeyError:
        raise err(409, "duplicate_code", "A cycle with this code already exists")
    c.id = str(res.inserted_id)
    await audit(request, user, "cycle.created", "cycle", c.id, after=c.model_dump(exclude={"id"}))
    return c.model_dump()


@router.patch("/cycles/{cycle_id}")
async def update_cycle(cycle_id: str, body: CyclePatch, request: Request, user: User = Depends(require("cycles.write"))):
    _id = oid(cycle_id)
    before = await db.cycles.find_one({"_id": _id})
    if not before:
        raise err(404, "not_found", "Cycle not found")
    if body.status == "active":
        await _active_conflict(_id)
    changes = {**CycleIn(**body.model_dump(exclude={"version"})).store(), "updated_at": now_utc()}
    try:
        res = await db.cycles.update_one({"_id": _id, "version": body.version}, {"$set": changes, "$inc": {"version": 1}})
    except DuplicateKeyError:
        raise err(409, "duplicate_code", "A cycle with this code already exists")
    if not res.matched_count:
        raise err(409, "stale_version", "This cycle was changed by someone else. Reload and try again.")
    after = await db.cycles.find_one({"_id": _id})
    await audit(request, user, "cycle.updated", "cycle", cycle_id, before=before, after=after)
    return Cycle.from_mongo(after).model_dump()


@router.get("/programs")
async def list_programs(cycle_id: Optional[str] = None, _: User = Depends(require("programs.read"))):
    q = {"cycle_id": cycle_id} if cycle_id else {}
    return [Program.from_mongo(d).model_dump() async for d in db.programs.find(q).sort([("route", 1), ("name", 1)])]


@router.post("/programs")
async def create_program(body: ProgramIn, request: Request, user: User = Depends(require("programs.write"))):
    if not await db.cycles.find_one({"_id": oid(body.cycle_id)}):
        raise err(422, "unknown_cycle", "Cycle not found")
    p = Program(**body.model_dump())
    try:
        res = await db.programs.insert_one(p.to_mongo())
    except DuplicateKeyError:
        raise err(409, "duplicate_code", "Program code already exists in this cycle")
    p.id = str(res.inserted_id)
    await audit(request, user, "program.created", "program", p.id, after=p.model_dump(exclude={"id"}))
    return p.model_dump()


@router.patch("/programs/{program_id}")
async def update_program(program_id: str, body: ProgramPatch, request: Request,
                         user: User = Depends(require("programs.write"))):
    _id = oid(program_id)
    before = await db.programs.find_one({"_id": _id})
    if not before:
        raise err(404, "not_found", "Program not found")
    changes = {**body.model_dump(exclude={"version"}), "updated_at": now_utc()}
    try:
        res = await db.programs.update_one({"_id": _id, "version": body.version}, {"$set": changes, "$inc": {"version": 1}})
    except DuplicateKeyError:
        raise err(409, "duplicate_code", "Program code already exists in this cycle")
    if not res.matched_count:
        raise err(409, "stale_version", "This program was changed by someone else. Reload and try again.")
    after = await db.programs.find_one({"_id": _id})
    await audit(request, user, "program.updated", "program", program_id, before=before, after=after)
    return Program.from_mongo(after).model_dump()


@router.get("/public/portal")
async def public_portal():
    c = Cycle.from_mongo(await db.cycles.find_one({"status": "active"}))
    if not c:
        return {"cycle": None, "programs": []}
    progs = [Program.from_mongo(d) async for d in db.programs.find({"cycle_id": c.id, "status": "active"}).sort("name", 1)]
    return {"cycle": c.model_dump(exclude={"version", "created_at", "updated_at"}),
            "programs": [p.model_dump(include={"id", "code", "name", "route", "campus", "duration_months",
                                                "seat_capacity", "tfw_seats", "stages", "application_fee_inr"}) for p in progs]}
