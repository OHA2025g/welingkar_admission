import os
import re
from datetime import timedelta

from bson import ObjectId

from core import IST, db, now_utc
from routes.config import Cycle, Program
from routes.policies import PolicyVersion
from security import User, audit, hash_password, verify_password

STAFF = [
    ("super_admin", "Meera Iyer", None),
    ("admissions_operator", "Rohan Kulkarni", "admissions"),
    ("document_verifier", "Sneha Patil", "verifier"),
    ("panelist", "Prof. Anil Deshpande", "panelist"),
    ("panelist", "Dr. Sunita Menon", "panelist2"),
    ("panelist", "Prof. Rajiv Bhatt", "panelist3"),
    ("interview_coordinator", "Kavita Rao", "coordinator"),
    ("accounts_operator", "Vikram Shah", "accounts"),
    ("result_approver", "Dr. Nandini Joshi", "results"),
    ("auditor", "Farhan Qureshi", "auditor"),
]
STAFF_DOMAIN = "weschool-demo.in"

CANDIDATES = [
    ("Aarav Mehta", "Maharashtra", "Mumbai", "verified"), ("Diya Sharma", "Delhi", "New Delhi", "verified"),
    ("Ishaan Nair", "Kerala", "Kochi", "verified"), ("Ananya Reddy", "Telangana", "Hyderabad", "verified"),
    ("Kabir Malhotra", "Punjab", "Ludhiana", "verified"), ("Saanvi Gupta", "Uttar Pradesh", "Lucknow", "verified"),
    ("Vihaan Joshi", "Karnataka", "Bengaluru", "verified"), ("Myra Banerjee", "West Bengal", "Kolkata", "partially_verified"),
    ("Arjun Pillai", "Tamil Nadu", "Chennai", "partially_verified"), ("Tara Kapoor", "Gujarat", "Ahmedabad", "registered"),
    ("Rhea Desai", "Maharashtra", "Pune", "verified"), ("Aditya Kulkarni", "Maharashtra", "Mumbai", "verified"),
    ("Neha Verma", "Madhya Pradesh", "Indore", "verified"), ("Siddharth Rao", "Karnataka", "Bengaluru", "verified"),
    ("Kunal Bose", "West Bengal", "Kolkata", "verified"), ("Pooja Iyer", "Tamil Nadu", "Chennai", "verified"),
    ("Manav Shah", "Gujarat", "Surat", "verified"), ("Isha Kulkarni", "Maharashtra", "Nagpur", "verified"),
]

PROGRAMS = [
    ("PGDM-MUM", "PGDM", "PGDM", "Mumbai", 24, 360, 18, ["application", "essay", "ga", "pi", "part_b"]),
    ("PGDM-BLR", "PGDM", "PGDM", "Bengaluru", 24, 240, 12, ["application", "essay", "ga", "pi", "part_b"]),
    ("PGDM-BD", "PGDM - Business Design", "PGDM", "Mumbai", 24, 60, 3, ["application", "essay", "pi", "part_b"]),
    ("PGDM-RBA", "PGDM - Research & Business Analytics", "PGDM", "Mumbai", 24, 60, 3, ["application", "essay", "pi", "part_b"]),
    ("PGDM-EB", "PGDM - E-Business", "PGDM", "Mumbai", 24, 60, 3, ["application", "essay", "pi", "part_b"]),
    ("PGDM-HC", "PGDM - Healthcare Management", "PGDM", "Mumbai", 24, 60, 3, ["application", "essay", "pi", "part_b"]),
    ("PGDM-ME", "PGDM - Media & Entertainment", "PGDM", "Mumbai", 24, 60, 3, ["application", "essay", "pi", "part_b"]),
    ("PGDM-RM", "PGDM - Retail Management", "PGDM", "Mumbai", 24, 60, 3, ["application", "essay", "pi", "part_b"]),
    ("PGDM-IB", "PGDM - International Business", "PGDM", "Mumbai", 24, 60, 3, ["application", "essay", "pi", "part_b"]),
    ("MMS-ACAP", "MMS (ACAP)", "MMS ACAP", "Mumbai", 24, 120, 6, ["application", "part_b"]),
    ("MMS-AGCAP", "MMS (Against CAP)", "MMS Against CAP", "Mumbai", 24, 30, 0, ["application", "part_b"]),
]

TFW_V1 = {"enabled": True, "seat_share_percent": 5, "family_income_limit_inr": 800000,
          "eligible_routes": ["PGDM", "MMS ACAP"],
          "required_documents": ["Family income certificate (current FY)", "Class X & XII marksheets",
                                 "Domicile certificate"],
          "notes": "Draft for D-05 approval. TFW seats are supernumerary within approved intake."}
REFUND_V1 = {"application_fee_refundable": False, "processing_fee_inr": 1000,
             "super_admin_signoff_above_inr": 50000,
             "tiers": [{"label": "15+ days before programme start", "days_before_start_min": 15, "refund_percent": 100},
                       {"label": "Up to 15 days before start", "days_before_start_min": 1, "refund_percent": 90},
                       {"label": "On or after start", "days_before_start_min": 0, "refund_percent": 0}],
             "notes": "Draft for D-08 approval; to align with the institute's approved refund rules."}
ADMISSION_V1 = {"programme_start_date": "2027-06-15", "on_hold_consumes_seat": True,
                "offline_modes": ["neft", "imps", "upi", "dd", "cheque"], "offline_verification_sla_days": 3,
                "notes": "D-07: on-hold seats count against capacity. Programme start drives refund tiers."}
SELECTION_V1 = {
    "exam_weight": 40, "ga_weight": 25, "pi_weight": 35, "selected_cutoff": 65, "waitlist_cutoff": 50,
    "ga_rubric": [{"key": "communication", "label": "Communication", "max": 10},
                  {"key": "content", "label": "Content & reasoning", "max": 10},
                  {"key": "leadership", "label": "Leadership & initiative", "max": 10},
                  {"key": "listening", "label": "Listening & team conduct", "max": 10}],
    "pi_rubric": [{"key": "career_clarity", "label": "Q1 · Career clarity", "max": 10},
                  {"key": "domain", "label": "Q2 · Academic / domain knowledge", "max": 10},
                  {"key": "communication", "label": "Q3 · Communication", "max": 10},
                  {"key": "awareness", "label": "Q4 · Business & current affairs", "max": 10},
                  {"key": "attitude", "label": "Q5 · Attitude & fit", "max": 10}],
    "pi_booking_cutoff_hours": 24, "pi_reschedule_limit": 2,
    "notes": "Draft for D-04 approval. Weights are renormalised when a programme has no GA stage; "
             "application-only routes (MMS) are not auto-shortlisted."}


async def _upsert_user(email: str, name: str, role: str, password: str, extra: dict | None = None) -> None:
    existing = await db.users.find_one({"email": email})
    if existing is None:
        await db.users.insert_one(User(email=email, name=name, role=role, password_hash=hash_password(password),
                                       created_by="seed", **(extra or {})).to_mongo())
    elif not verify_password(password, existing["password_hash"]):
        await db.users.update_one({"_id": existing["_id"]}, {"$set": {"password_hash": hash_password(password)}})


async def seed():
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    for role, name, slug in STAFF:
        email = admin_email if role == "super_admin" else f"{slug}@{STAFF_DOMAIN}"
        pw = os.environ["ADMIN_PASSWORD"] if role == "super_admin" else os.environ["SEED_STAFF_PASSWORD"]
        await _upsert_user(email, name, role, pw)
    await _upsert_user("delivered+accounts@resend.dev", "Accounts Step-up Tester", "accounts_operator", os.environ["SEED_STAFF_PASSWORD"])

    for i, (name, state, city, status) in enumerate(CANDIDATES, start=1):
        now = now_utc()
        await _upsert_user(f"candidate{i:02d}@example.com", name, "candidate", os.environ["SEED_CANDIDATE_PASSWORD"], {
            "mobile": f"+9198200{i:05d}", "state": state, "city": city, "identity_status": status,
            "candidate_ref": f"WS-C-26-S{i:04d}",
            "email_verified_at": now if status != "registered" else None,
            "whatsapp_verified_at": now if status == "verified" else None})

    if not await db.cycles.find_one({}):
        c = Cycle(code="2026-28", name="PGDM & MMS Admissions 2026-28", status="active",
                  application_open="2025-09-01", application_close="2026-02-28", part_b_open="2026-03-15",
                  part_b_close="2026-06-15", application_fee_inr=float(os.environ["APPLICATION_FEE_INR"]),
                  admission_fee_inr=100000)
        res = await db.cycles.insert_one(c.to_mongo())
        await audit(None, None, "cycle.created", "cycle", str(res.inserted_id), after=c.model_dump(exclude={"id"}),
                    reason="seed")
    due = (now_utc().astimezone(IST).date() + timedelta(days=14)).isoformat()
    await db.cycles.update_one(
        {"code": "2026-28", "$or": [{"admission_fee_due": {"$exists": False}}, {"admission_fee_due": None}]},
        {"$set": {"admission_fee_due": due}})
    cycle = await db.cycles.find_one({"code": "2026-28"})
    if cycle and not await db.programs.find_one({"cycle_id": str(cycle["_id"])}):
        for code, name, route, campus, dur, seats, tfw, stages in PROGRAMS:
            await db.programs.insert_one(Program(cycle_id=str(cycle["_id"]), code=code, name=name, route=route,
                                                 campus=campus, duration_months=dur, seat_capacity=seats,
                                                 tfw_seats=tfw, stages=stages).to_mongo())

    for key, content in (("tfw_rules", TFW_V1), ("refund_policy", REFUND_V1), ("selection_rules", SELECTION_V1),
                         ("admission_rules", ADMISSION_V1)):
        if not await db.policy_versions.find_one({"key": key}):
            await db.policy_versions.insert_one(PolicyVersion(
                key=key, version=1, status="active", content=content, change_note="Initial baseline (seed)",
                created_by="seed", activated_at=now_utc(), activated_by="seed").to_mongo())
    await db.policy_versions.update_one(
        {"key": "refund_policy", "status": "active", "content.super_admin_signoff_above_inr": {"$exists": False}},
        {"$set": {"content.super_admin_signoff_above_inr": 50000}})


async def ensure_auth_indexes():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("mobile", unique=True, partialFilterExpression={"role": "candidate"})
    await db.login_attempts.create_index("identifier")
    await db.sessions.create_index("sid", unique=True)
    await db.sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.audit_log.create_index([("at", -1)])
    await db.audit_log.create_index("action")
    await db.cycles.create_index("code", unique=True)
    await db.programs.create_index([("cycle_id", 1), ("code", 1)], unique=True)
    await db.policy_versions.create_index([("key", 1), ("version", 1)], unique=True)
    await db.applications.create_index([("candidate_id", 1), ("cycle_id", 1)], unique=True)
    await db.application_versions.create_index([("application_id", 1), ("version", 1)], unique=True)
    await db.payment_orders.create_index("candidate_id")
