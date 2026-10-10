import io
import logging
import uuid

from bson import ObjectId
from PIL import Image, ImageDraw

from core import db, now_utc
from routes.application import Application, snapshot, write_version
from routes.payments import PaymentOrder
from services import storage

logger = logging.getLogger(__name__)

# candidate index -> stage
STAGES = {1: "draft", 2: "paid_draft", 3: "submitted", 4: "submitted_post", 5: "paid", 7: "submitted",
          11: "submitted", 12: "submitted", 13: "submitted", 14: "submitted",
          15: "submitted", 16: "submitted", 17: "submitted", 18: "submitted"}
PREFS = [["PGDM-MUM", "PGDM-BD", "PGDM-RBA"], ["PGDM-RBA", "PGDM-EB"], ["PGDM-HC", "PGDM-MUM"],
         ["PGDM-ME", "PGDM-BLR"], ["PGDM-BLR", "PGDM-IB"], ["MMS-ACAP"], ["PGDM-EB", "PGDM-RM", "PGDM-MUM"]]


def sample_sections(i: int, u: dict) -> dict:
    return {
        "personal": {"full_name": u["name"], "dob": f"{2000 + i % 3}-0{1 + i % 9}-1{i % 9}", "gender": "Female" if i % 2 == 0 else "Male",
                     "category": ["General", "OBC-NCL", "EWS"][i % 3], "nationality": "Indian", "pwd": False},
        "family": {"father_name": f"Mr. {u['name'].split()[-1]}", "father_occupation": "Business",
                   "mother_name": f"Mrs. {u['name'].split()[-1]}", "mother_occupation": "Teacher",
                   "annual_family_income_inr": 600000 + i * 150000, "siblings": [{"name": "Riya", "relation": "Sister", "occupation": "Student"}]},
        "contact": {"address_line1": f"{10 + i}, Shanti Niketan Society", "address_line2": "Main Road", "city": u["city"],
                    "state": u["state"], "pincode": f"4000{10 + i}", "alternate_mobile": "",
                    "emergency_contact_name": f"Mr. {u['name'].split()[-1]}", "emergency_contact_mobile": f"98765{43200 + i}"},
        "education": {"class_x": {"board": "CBSE", "school": "Kendriya Vidyalaya", "year": 2016 + i % 3, "percentage": 85 + i % 10},
                      "class_xii": {"board": "State Board", "school": "City Junior College", "year": 2018 + i % 3, "percentage": 80 + i % 12},
                      "graduation": {"degree": "B.Com", "discipline": "Accounting & Finance", "university": "University of Mumbai",
                                     "status": "completed", "year": 2021 + i % 3, "score_type": "cgpa", "score": 7.5 + (i % 5) / 4}},
        "work": {"has_experience": i % 2 == 1, "experiences": [{"organization": "Infosys", "designation": "Analyst", "sector": "IT Services",
                                                                 "start": "2023-07", "end": ""}] if i % 2 == 1 else []},
        "exams": {"exams": [{"exam": "CAT", "year": 2025, "roll_number": f"CAT25{1000 + i}", "status": "appeared", "score": None,
                             "percentile": 88.5 + i if i < 10 else round(80 + (i * 3.7) % 19, 2)}]},
        "preferences": {"ranked": ["MMS-AGCAP"] if i >= 15 else PREFS[(i - 1) % len(PREFS)]},
    }


def _image(text: str, size: tuple, color: str) -> bytes:
    img = Image.new("RGB", size, color)
    ImageDraw.Draw(img).text((size[0] // 3, size[1] // 2 - 6), text, fill="white")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


async def _upload(cid: str, kind: str, data: bytes):
    try:
        stored = await storage.put_object(f"{storage.APP_NAME}/candidates/{cid}/{kind}-{uuid.uuid4().hex}.jpg", data, "image/jpeg")
    except Exception as e:
        logger.warning(f"seed upload skipped: {e}")
        return None
    res = await db.files.insert_one({"owner_id": cid, "kind": kind, "storage_path": stored["path"], "content_type": "image/jpeg",
                                     "size": len(data), "original_filename": f"{kind}.jpg", "is_deleted": False, "created_at": now_utc()})
    return str(res.inserted_id)


async def _paid_order(u: dict, app: Application, fee: float):
    key = f"seed-appfee-{u['_id']}"
    if await db.payment_orders.find_one({"idempotency_key": key}):
        return
    now = now_utc()
    await db.payment_orders.insert_one(PaymentOrder(
        order_ref=f"WS-PAY-SEED-{u['candidate_ref'][-4:]}", fee_code="application_fee", description="WeSchool Application Fee (2026-28)",
        amount_paise=int(fee * 100), candidate_name=u["name"], candidate_email=u["email"], candidate_id=str(u["_id"]),
        application_ref=app.application_ref, provider="seed", status="paid", verified_via="seed", idempotency_key=key,
        payload_hash="seed", created_at=now, updated_at=now, paid_at=now).to_mongo())


async def reset_candidate(i: int):
    u = await db.users.find_one({"email": f"candidate{i:02d}@example.com"})
    a = await db.applications.find_one({"candidate_id": str(u["_id"])})
    if a:
        await db.application_versions.delete_many({"application_id": str(a["_id"])})
        await db.applications.delete_one({"_id": a["_id"]})
    await seed_applications()


async def seed_applications():
    cycle = await db.cycles.find_one({"code": "2026-28"})
    if not cycle:
        return
    if cycle["application_close"] == "2026-02-28":
        await db.cycles.update_one({"_id": cycle["_id"]}, {"$set": {
            "application_open": "2026-08-01", "application_close": "2027-01-31", "part_b_open": "2027-03-01", "part_b_close": "2027-06-15"}})
    cid = str(cycle["_id"])
    for i, stage in STAGES.items():
        u = await db.users.find_one({"email": f"candidate{i:02d}@example.com"})
        if not u:
            continue
        existing = Application.from_mongo(await db.applications.find_one({"candidate_id": str(u["_id"])}))
        if existing:
            if stage != "draft":
                await _paid_order(u, existing, cycle["application_fee_inr"])
            if existing.status == "submitted" and not await db.application_versions.find_one({"application_id": existing.id}):
                await write_version(existing.id, 1, await snapshot(existing, u), "submission (seed)", "seed")
            continue
        secs = sample_sections(i, u)
        keys = ["personal", "family", "contact"] if stage == "draft" else (
            list(secs)[:5] if stage == "paid_draft" else ([] if stage == "paid" else list(secs)))
        app = Application(candidate_id=str(u["_id"]), cycle_id=cid, application_ref=f"WS-2026-28-S{i:05d}",
                          sections={k: secs[k] for k in keys}, section_status={k: "complete" for k in keys})
        if stage.startswith("submitted"):
            app.photo_file_id = await _upload(str(u["_id"]), "photo", _image(u["name"][:2].upper(), (300, 360), "#9E1B32"))
            app.signature_file_id = await _upload(str(u["_id"]), "signature", _image(u["name"].split()[0], (400, 120), "#0F172A"))
            app.status, app.submitted_at, app.submitted_version = "submitted", now_utc(), 1
        if stage == "submitted_post":
            now = now_utc()
            app.post = {"declaration": {"version": "PGDM-DECL-2026-28-v1", "accepted_at": now},
                        "confirmation": {"version": 1, "confirmed_at": now}}
        res = await db.applications.insert_one(app.to_mongo())
        app.id = str(res.inserted_id)
        if stage != "draft":
            await _paid_order(u, app, cycle["application_fee_inr"])
        if app.status == "submitted":
            await write_version(app.id, 1, await snapshot(app, u), "submission (seed)", "seed")
