import asyncio
import uuid
from datetime import datetime
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field

from core import BaseDocument, db, now_utc
from routes.partb import active_consent, eligibility_for
from routes.policies import active_policy
from security import User, audit, err, require
from services import storage
from services.notify import notify

router = APIRouter(prefix="/api", tags=["partb-documents"])
STAGES = ("initial", "admission")
STAGE_LABEL = {"initial": "Counselling documents", "admission": "Admission documents"}
ADMISSION_DOCS = [("medical", "Medical fitness certificate"), ("undertaking", "Anti-ragging undertaking (signed)"),
                  ("migration", "Migration / transfer certificate")]
MAGIC = {b"%PDF": "application/pdf", b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png"}


class PartBDoc(BaseDocument):
    candidate_id: str
    stage: str
    doc_key: str
    label: str
    file_id: str
    content_type: str
    version: int = 1
    status: str = "registered"
    remarks: Optional[str] = None
    superseded: list[dict] = []
    history: list[dict] = []
    uploaded_at: datetime = Field(default_factory=now_utc)
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None


async def checklist(cid: str, stage: str) -> list[dict]:
    if stage == "admission":
        return [{"key": k, "label": label} for k, label in ADMISSION_DOCS]
    app = await db.applications.find_one({"candidate_id": cid}) or {}
    s = app.get("sections", {})
    rows = await eligibility_for(cid)
    items = [("id_proof", "Government photo ID (Aadhaar / PAN / Passport)")]
    if any(e.outcome == "selected" for e in rows):
        items += [("class_x", "Class X marksheet"), ("class_xii", "Class XII marksheet")]
    grad = (s.get("education") or {}).get("graduation") or {}
    items.append(("graduation", "Final-year marksheets + bonafide certificate" if grad.get("status") == "final_year"
                  else "Graduation marksheets / degree certificate"))
    if any(e.outcome == "selected" for e in rows):
        if (s.get("personal") or {}).get("category") not in (None, "General"):
            items.append(("category", "Category certificate (current, valid)"))
        if (s.get("work") or {}).get("has_experience"):
            items.append(("work", "Work experience letter(s)"))
        _, tfw = await active_policy("tfw_rules")
        income = (s.get("family") or {}).get("annual_family_income_inr")
        if tfw.get("enabled") and income is not None and income <= tfw["family_income_limit_inr"]:
            items.append(("tfw_income", "Family income certificate (current FY) for TFW"))
    return [{"key": k, "label": label} for k, label in items]


async def stage_status(cid: str, stage: str) -> dict:
    req = await checklist(cid, stage)
    docs = {d["doc_key"]: d async for d in db.partb_documents.find({"candidate_id": cid, "stage": stage})}
    st = [docs[r["key"]]["status"] for r in req if r["key"] in docs]
    if not st:
        s = "not_started"
    elif "discrepancy" in st:
        s = "discrepancy"
    elif len(st) < len(req):
        s = "incomplete"
    elif all(x == "verified" for x in st):
        s = "verified"
    else:
        s = "registered"
    return {"status": s, "required": len(req), "uploaded": len(st), "verified": st.count("verified"), "discrepancy": st.count("discrepancy")}


async def stage_lock(cid: str, stage: str) -> Optional[str]:
    if stage == "initial":
        c = await active_consent(cid)
        return None if c and c.overall else "Give your course and overall admission consent first"
    a = await db.partb_allotments.find_one({"candidate_id": cid, "seat_held": True, "status": {"$in": ["allotted", "provisional"]}})
    return None if a else "Admission documents open after a seat is allotted"


def _stage(stage: str) -> str:
    if stage not in STAGES:
        raise err(404, "unknown_stage", "Unknown document stage")
    return stage


async def docs_view(cid: str, stage: str) -> dict:
    req = await checklist(cid, stage)
    docs = {d["doc_key"]: PartBDoc.from_mongo(d) async for d in db.partb_documents.find({"candidate_id": cid, "stage": stage})}
    items = [{**r, "doc": docs[r["key"]].model_dump(exclude={"history"}) if r["key"] in docs else None} for r in req]
    return {"stage": stage, "title": STAGE_LABEL[stage], "items": items, "summary": await stage_status(cid, stage),
            "locked_reason": await stage_lock(cid, stage)}


@router.get("/candidate/partb/documents/{stage}")
async def my_docs(stage: str, user: User = Depends(require("self.application"))):
    return await docs_view(user.id, _stage(stage))


@router.post("/candidate/partb/documents/{stage}/{key}")
async def upload_doc(stage: str, key: str, request: Request, file: UploadFile = File(...), user: User = Depends(require("self.application"))):
    _stage(stage)
    reason = await stage_lock(user.id, stage)
    if reason:
        raise err(409, "stage_locked", reason)
    item = next((r for r in await checklist(user.id, stage) if r["key"] == key), None)
    if not item:
        raise err(404, "not_required", "This document is not on your checklist")
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise err(422, "too_large", "Documents must be 2 MB or smaller")
    if len(data) < 1_000:
        raise err(422, "too_small", "File looks empty or corrupted")
    ctype = next((t for m, t in MAGIC.items() if data.startswith(m)), None)
    if not ctype:
        raise err(422, "invalid_type", "Upload a PDF, JPG or PNG file")
    cur = PartBDoc.from_mongo(await db.partb_documents.find_one({"candidate_id": user.id, "stage": stage, "doc_key": key}))
    if cur and cur.status == "verified":
        raise err(409, "already_verified", "This document is verified and cannot be replaced")
    ext = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[ctype]
    try:
        stored = await storage.put_object(f"{storage.APP_NAME}/partb/{user.id}/{stage}-{key}-{uuid.uuid4().hex}.{ext}", data, ctype)
    except Exception:
        raise err(503, "storage_unavailable", "Upload failed. Please try again.")
    fid = str((await db.files.insert_one({"owner_id": user.id, "kind": "partb_doc", "storage_path": stored["path"], "content_type": ctype,
                                          "size": len(data), "original_filename": file.filename, "is_deleted": False,
                                          "quarantine": False, "downloadable": True, "created_at": now_utc()})).inserted_id)
    now = now_utc()
    if cur:
        res = await db.partb_documents.update_one({"_id": ObjectId(cur.id), "version": cur.version, "status": {"$ne": "verified"}}, {
            "$set": {"file_id": fid, "content_type": ctype, "version": cur.version + 1, "status": "registered", "remarks": None,
                     "uploaded_at": now, "reviewed_by": None, "reviewed_at": None},
            "$push": {"superseded": {"file_id": cur.file_id, "version": cur.version, "status": cur.status, "remarks": cur.remarks, "at": now},
                      "history": {"action": "reuploaded", "version": cur.version + 1, "by": user.email, "at": now}}})
        if not res.modified_count:
            raise err(409, "stale", "Document changed meanwhile. Reload and try again.")
    else:
        await db.partb_documents.insert_one(PartBDoc(candidate_id=user.id, stage=stage, doc_key=key, label=item["label"], file_id=fid,
                                                     content_type=ctype, history=[{"action": "uploaded", "version": 1, "by": user.email,
                                                                                   "at": now}]).to_mongo())
    await audit(request, user, "partb.document_uploaded", "partb_document", f"{stage}:{key}", after={"file_id": fid, "size": len(data)})
    return await docs_view(user.id, stage)


# ---------- verifier ----------
@router.get("/verify/worklist")
async def worklist(stage: str = "initial", list: Literal["registered", "discrepancy", "verified"] = "registered",
                   _: User = Depends(require("documents.verify"))):
    _stage(stage)
    cids = await db.partb_documents.distinct("candidate_id", {"stage": stage})
    statuses = await asyncio.gather(*(stage_status(cid, stage) for cid in cids)) if cids else []
    out, counts, wanted = [], {"registered": 0, "discrepancy": 0, "verified": 0}, []
    for cid, s in zip(cids, statuses):
        bucket = "registered" if s["status"] in ("registered", "incomplete") else s["status"]
        if bucket not in counts:
            continue
        counts[bucket] += 1
        if bucket == list:
            wanted.append((cid, s))
    users, latest = {}, {}
    if wanted:
        ids = [ObjectId(cid) for cid, _ in wanted if ObjectId.is_valid(cid)]
        users = {str(u["_id"]): u async for u in db.users.find({"_id": {"$in": ids}}, {"name": 1, "candidate_ref": 1})} if ids else {}
        async for doc in db.partb_documents.find(
                {"candidate_id": {"$in": [cid for cid, _ in wanted]}, "stage": stage},
                {"candidate_id": 1, "uploaded_at": 1}).sort("uploaded_at", -1):
            latest.setdefault(doc["candidate_id"], doc)
    for cid, s in wanted:
        u = users[cid]
        out.append({"candidate_id": cid, "name": u["name"], "candidate_ref": u.get("candidate_ref"), **s,
                    "stage_status": s["status"], "last_upload": latest[cid]["uploaded_at"]})
    return {"stage": stage, "list": list, "counts": counts, "rows": sorted(out, key=lambda r: r["last_upload"])}


@router.get("/verify/candidates/{cid}")
async def verify_candidate(cid: str, stage: str = "initial", _: User = Depends(require("documents.verify"))):
    u = await db.users.find_one({"_id": ObjectId(cid), "role": "candidate"}) if ObjectId.is_valid(cid) else None
    if not u or not await db.partb_documents.find_one({"candidate_id": cid}):
        raise err(404, "not_found", "Candidate not in any verification worklist")
    app = await db.applications.find_one({"candidate_id": cid}, {"application_ref": 1, "sections.personal": 1})
    view = await docs_view(cid, _stage(stage))
    hist = {d["doc_key"]: d.get("history", []) async for d in db.partb_documents.find({"candidate_id": cid, "stage": stage})}
    for it in view["items"]:
        it["history"] = hist.get(it["key"], [])
    p = (app or {}).get("sections", {}).get("personal", {})
    return {"candidate": {"id": cid, "name": u["name"], "candidate_ref": u.get("candidate_ref"), "application_ref": (app or {}).get("application_ref"),
                          "category": p.get("category"), "dob": p.get("dob")}, **view}


class ReviewIn(BaseModel):
    status: Literal["verified", "discrepancy"]
    remarks: str = Field("", max_length=500)
    version: int


@router.post("/verify/documents/{doc_id}")
async def review_doc(doc_id: str, body: ReviewIn, request: Request, user: User = Depends(require("documents.verify"))):
    d = PartBDoc.from_mongo(await db.partb_documents.find_one({"_id": ObjectId(doc_id)})) if ObjectId.is_valid(doc_id) else None
    if not d:
        raise err(404, "not_found", "Document not found")
    if body.status == "discrepancy" and len(body.remarks.strip()) < 5:
        raise err(422, "remarks_required", "Explain the discrepancy so the candidate knows what to re-upload")
    if d.status == "verified":
        raise err(409, "already_verified", "Document is already verified")
    now = now_utc()
    res = await db.partb_documents.update_one({"_id": ObjectId(d.id), "version": body.version, "status": {"$ne": "verified"}}, {
        "$set": {"status": body.status, "remarks": body.remarks.strip() or None, "reviewed_by": user.email, "reviewed_at": now},
        "$push": {"history": {"action": body.status, "version": d.version, "remarks": body.remarks.strip() or None, "by": user.email, "at": now}}})
    if not res.modified_count:
        raise err(409, "stale", "A newer version was uploaded or it was already reviewed. Reload.")
    await audit(request, user, f"partb.document_{body.status}", "partb_document", d.id, before={"status": d.status},
                after={"status": body.status, "remarks": body.remarks}, reason=body.remarks or None)
    if body.status == "discrepancy":
        await notify(d.candidate_id, "discrepancy", f"Re-upload needed: {d.label}", f"Reviewer remark: {body.remarks.strip()}", email=True)
    elif (await stage_status(d.candidate_id, d.stage))["status"] == "verified":
        await notify(d.candidate_id, "verified", f"{STAGE_LABEL[d.stage]} verified", "All your documents for this stage are verified.")
    return await verify_candidate(d.candidate_id, d.stage, user)
