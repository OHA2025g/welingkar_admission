from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from pymongo.errors import DuplicateKeyError

from core import BaseDocument, db, now_utc
from security import User, audit, err, require

router = APIRouter(prefix="/api/policies", tags=["policies"])


class TfwPolicy(BaseModel):
    enabled: bool = True
    seat_share_percent: float = Field(ge=0, le=100)
    family_income_limit_inr: float = Field(ge=0)
    eligible_routes: list[str] = []
    required_documents: list[str] = []
    notes: str = ""


class RefundTier(BaseModel):
    label: str = Field(min_length=2)
    days_before_start_min: int = Field(ge=0)
    refund_percent: float = Field(ge=0, le=100)


class RefundPolicy(BaseModel):
    application_fee_refundable: bool = False
    processing_fee_inr: float = Field(ge=0)
    super_admin_signoff_above_inr: float = Field(default=50000, ge=0)
    tiers: list[RefundTier] = Field(min_length=1)
    notes: str = ""

    @model_validator(mode="after")
    def unique_days(self):
        days = [t.days_before_start_min for t in self.tiers]
        if len(days) != len(set(days)):
            raise ValueError("Each tier needs a distinct 'days before start' threshold")
        self.tiers.sort(key=lambda t: -t.days_before_start_min)
        return self


class Criterion(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,29}$")
    label: str = Field(min_length=2, max_length=80)
    max: int = Field(ge=1, le=100)


class SelectionRules(BaseModel):
    exam_weight: float = Field(ge=0, le=100)
    ga_weight: float = Field(ge=0, le=100)
    pi_weight: float = Field(ge=0, le=100)
    selected_cutoff: float = Field(ge=0, le=100)
    waitlist_cutoff: float = Field(ge=0, le=100)
    ga_rubric: list[Criterion] = Field(min_length=1)
    pi_rubric: list[Criterion] = Field(min_length=1)
    pi_booking_cutoff_hours: int = Field(ge=0, le=240)
    pi_reschedule_limit: int = Field(ge=0, le=10)
    notes: str = ""

    @model_validator(mode="after")
    def check(self):
        if round(self.exam_weight + self.ga_weight + self.pi_weight, 4) != 100:
            raise ValueError("Exam, GA and PI weights must add up to 100")
        if self.waitlist_cutoff > self.selected_cutoff:
            raise ValueError("Waitlist cut-off cannot exceed the selection cut-off")
        for rub in (self.ga_rubric, self.pi_rubric):
            if len({c.key for c in rub}) != len(rub):
                raise ValueError("Rubric keys must be unique")
        return self


class AdmissionRules(BaseModel):
    programme_start_date: str = Field(pattern=r"^20\d{2}-[01]\d-[0-3]\d$")
    on_hold_consumes_seat: bool = True
    offline_modes: list[Literal["neft", "imps", "upi", "dd", "cheque", "cash"]] = Field(min_length=1)
    offline_verification_sla_days: int = Field(ge=1, le=30)
    notes: str = ""


POLICIES = {
    "admission_rules": {"title": "Admission, seat-hold & offline payment rules", "schema": AdmissionRules},
    "tfw_rules": {"title": "Tuition Fee Waiver (TFW) rules", "schema": TfwPolicy},
    "refund_policy": {"title": "Refund policy", "schema": RefundPolicy},
    "selection_rules": {"title": "Selection rules, rubric & interview settings", "schema": SelectionRules},
}


async def active_policy(key: str) -> tuple[int, dict]:
    p = await db.policy_versions.find_one({"key": key, "status": "active"})
    if not p:
        raise err(409, "policy_missing", f"No active '{key}' policy")
    return p["version"], p["content"]


class PolicyVersion(BaseDocument):
    key: str
    version: int
    status: Literal["draft", "active", "superseded"]
    content: dict[str, Any]
    change_note: str
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=now_utc)
    activated_at: Optional[datetime] = None
    activated_by: Optional[str] = None


class PolicyDraftIn(BaseModel):
    content: dict[str, Any]
    change_note: str = Field(min_length=3, max_length=300)


def _key(key: str) -> dict:
    if key not in POLICIES:
        raise err(404, "unknown_policy", "Unknown policy")
    return POLICIES[key]


@router.get("")
async def list_policies(_: User = Depends(require("policies.read"))):
    out = []
    for key, meta in POLICIES.items():
        active = PolicyVersion.from_mongo(await db.policy_versions.find_one({"key": key, "status": "active"}))
        latest = PolicyVersion.from_mongo(await db.policy_versions.find_one({"key": key}, sort=[("version", -1)]))
        out.append({"key": key, "title": meta["title"], "active": active.model_dump() if active else None,
                    "latest_version": latest.version if latest else 0})
    return out


@router.get("/{key}/versions")
async def versions(key: str, _: User = Depends(require("policies.read"))):
    _key(key)
    return [PolicyVersion.from_mongo(d).model_dump() async for d in db.policy_versions.find({"key": key}).sort("version", -1)]


@router.post("/{key}/versions")
async def create_draft(key: str, body: PolicyDraftIn, request: Request, user: User = Depends(require("policies.write"))):
    meta = _key(key)
    try:
        content = meta["schema"](**body.content).model_dump()
    except ValueError as e:
        raise err(422, "invalid_policy", str(e).split("\n")[-1] if "\n" in str(e) else str(e))
    latest = await db.policy_versions.find_one({"key": key}, sort=[("version", -1)])
    pv = PolicyVersion(key=key, version=(latest["version"] + 1) if latest else 1, status="draft", content=content,
                       change_note=body.change_note, created_by=user.email)
    try:
        res = await db.policy_versions.insert_one(pv.to_mongo())
    except DuplicateKeyError:
        raise err(409, "stale_version", "Another draft was just created. Reload and try again.")
    pv.id = str(res.inserted_id)
    await audit(request, user, "policy.draft_created", "policy", f"{key}:v{pv.version}", after=content,
                reason=body.change_note)
    return pv.model_dump()


@router.post("/{key}/versions/{version}/activate")
async def activate(key: str, version: int, request: Request, user: User = Depends(require("policies.write"))):
    _key(key)
    target = await db.policy_versions.find_one({"key": key, "version": version})
    if not target:
        raise err(404, "not_found", "Version not found")
    if target["status"] != "draft":
        raise err(409, "not_draft", "Only draft versions can be activated")
    prev = await db.policy_versions.find_one({"key": key, "status": "active"})
    res = await db.policy_versions.update_one({"_id": target["_id"], "status": "draft"}, {"$set": {
        "status": "active", "activated_at": now_utc(), "activated_by": user.email}})
    if not res.modified_count:
        raise err(409, "not_draft", "Version was already activated")
    await db.policy_versions.update_many({"key": key, "status": "active", "_id": {"$ne": target["_id"]}},
                                         {"$set": {"status": "superseded"}})
    await audit(request, user, "policy.activated", "policy", f"{key}:v{version}",
                before=prev["content"] if prev else None, after=target["content"],
                reason=f"v{prev['version'] if prev else 0} -> v{version}: {target['change_note']}")
    return PolicyVersion.from_mongo(await db.policy_versions.find_one({"_id": target["_id"]})).model_dump()
