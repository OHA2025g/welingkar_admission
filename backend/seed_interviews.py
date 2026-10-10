import logging
from datetime import datetime, timedelta

from bson import ObjectId

from app_schema import PIQ
from core import IST, db, now_utc
from routes.interviews import Booking, Location, Room, Session
from routes.policies import active_policy
from routes.results import generate_version, transition

logger = logging.getLogger(__name__)
SCORED = (3, 4, 7, 11)
BIAS = {3: 2, 4: 0, 7: 1, 11: -3}


async def ensure_interview_indexes():
    await db.interview_bookings.create_index([("application_id", 1), ("type", 1)], unique=True)
    await db.interview_bookings.create_index("session_id")
    await db.interview_sessions.create_index([("date", 1), ("start", 1)])
    await db.interview_sessions.create_index("panelist_ids")
    await db.assessments.create_index([("session_id", 1), ("application_id", 1), ("panelist_id", 1)], unique=True)
    await db.result_versions.create_index([("cycle_id", 1), ("version", 1)], unique=True)


async def seed_interviews():
    if await db.interview_locations.find_one({}):
        return
    cycle = await db.cycles.find_one({"code": "2026-28"})
    if not cycle:
        return
    cid = str(cycle["_id"])
    apps, users = {}, {}
    for i in (3, 4, 7, 11, 12, 13, 14):
        u = await db.users.find_one({"email": f"candidate{i:02d}@example.com"})
        a = await db.applications.find_one({"candidate_id": str(u["_id"]), "status": "submitted"}) if u else None
        if not a:
            logger.warning(f"seed_interviews skipped: candidate{i:02d} has no submitted application")
            return
        apps[i], users[i] = a, u
    now = now_utc()
    for i in (3, 4, 7, 11, 12, 14):
        answers = {q["id"]: f"Seeded answer from {users[i]['name']} about {q['label'].lower()} with a concrete example." for q in PIQ}
        await db.applications.update_one({"_id": apps[i]["_id"]}, {"$set": {"post.piq": {"answers": answers, "saved_at": now, "submitted_at": now}}})
    for i in (7, 11):
        await db.applications.update_one({"_id": apps[i]["_id"]}, {"$set": {"sections.family.annual_family_income_inr": 450000}})

    pan = [str((await db.users.find_one({"email": f"{s}@weschool-demo.in"}))["_id"]) for s in ("panelist", "panelist2", "panelist3")]
    locs, rooms = {}, {}
    for key, name, city, addr, rs in (
            ("MUM", "WeSchool Mumbai (Matunga)", "Mumbai", "L. Napoo Road, Matunga (East), Mumbai 400019",
             [("GA Hall 1", 12), ("PI Room 101", 6), ("PI Room 102", 6)]),
            ("BLR", "WeSchool Bengaluru (Electronic City)", "Bengaluru", "Electronics City Phase 1, Bengaluru 560100",
             [("GA Hall B1", 10), ("PI Room B201", 5)])):
        locs[key] = str((await db.interview_locations.insert_one(Location(cycle_id=cid, name=name, city=city, address=addr).to_mongo())).inserted_id)
        for rn, cap in rs:
            rooms[rn] = (locs[key], str((await db.interview_rooms.insert_one(Room(location_id=locs[key], name=rn, capacity=cap).to_mongo())).inserted_id))
    d0 = datetime.now(IST).date()

    async def S(type, room, offset, start, end, cap, pids):
        loc_id, room_id = rooms[room]
        s = Session(cycle_id=cid, type=type, location_id=loc_id, room_id=room_id, date=(d0 + timedelta(days=offset)).isoformat(),
                    start=start, end=end, capacity=cap, panelist_ids=pids, created_by="seed")
        return str((await db.interview_sessions.insert_one(s.to_mongo())).inserted_id)

    s1 = await S("GA", "GA Hall 1", -6, "10:00", "12:00", 12, [pan[0], pan[1]])
    s2 = await S("PI", "PI Room 101", -5, "10:00", "13:00", 6, [pan[0]])
    s3 = await S("PI", "PI Room 102", -1, "14:00", "17:00", 6, [pan[1]])
    await S("GA", "GA Hall 1", 7, "10:00", "12:00", 12, [pan[0], pan[1]])
    await S("PI", "PI Room 101", 8, "10:00", "13:00", 4, [pan[0]])
    await S("PI", "PI Room 102", 8, "14:00", "17:00", 4, [pan[2]])
    await S("PI", "PI Room B201", 9, "10:00", "11:00", 1, [pan[2]])
    await S("GA", "GA Hall B1", 9, "14:00", "16:00", 10, [pan[2]])

    async def book(i, type, sid):
        s = await db.interview_sessions.find_one_and_update({"_id": ObjectId(sid)}, {"$inc": {"booked": 1}})
        b = Booking(cycle_id=cid, application_id=str(apps[i]["_id"]), candidate_id=str(users[i]["_id"]), type=type, session_id=sid,
                    source="seed", attendance="present", attendance_at=now,
                    history=[{"action": "allocated", "session_id": sid, "slot": f"{s['date']} {s['start']}", "version": 1, "at": now, "by": "seed"}])
        await db.interview_bookings.insert_one(b.to_mongo())

    for i in (3, 4, 7, 11, 12):
        await book(i, "GA", s1)
    for i in SCORED:
        await book(i, "PI", s2)
    await book(12, "PI", s3)
    for sid, pids in ((s1, pan[:2]), (s2, pan[:1]), (s3, pan[1:2])):
        await db.interview_sessions.update_one({"_id": ObjectId(sid)}, {"$set": {
            f"panelist_attendance.{p}": {"status": "present", "at": now, "by": "seed"} for p in pids}})

    rv, rules = await active_policy("selection_rules")
    names = {p: (await db.users.find_one({"_id": ObjectId(p)}))["name"] for p in pan}
    for type, sid, pids, rub in (("GA", s1, pan[:2], rules["ga_rubric"]), ("PI", s2, pan[:1], rules["pi_rubric"])):
        mx = sum(c["max"] for c in rub)
        for i in SCORED:
            for j, p in enumerate(pids):
                scores = {c["key"]: max(0, min(c["max"], 5 + BIAS[i] + (k + j) % 3)) for k, c in enumerate(rub)}
                total = sum(scores.values())
                await db.assessments.insert_one({
                    "cycle_id": cid, "session_id": sid, "type": type, "application_id": str(apps[i]["_id"]),
                    "candidate_id": str(users[i]["_id"]), "panelist_id": p, "panelist_name": names[p], "scores": scores,
                    "total": float(total), "max_total": mx, "normalized": round(100 * total / mx, 2), "rubric_version": rv,
                    "status": "submitted", "version": 1, "submitted_at": now, "corrections": [], "created_at": now, "updated_at": now})

    op = "admissions@weschool-demo.in"
    v1 = await generate_version(op, "Initial merit run after GA/PI (seed)")
    await transition(v1.version, "generated", "approved", "results@weschool-demo.in")
    await transition(v1.version, "approved", "published", "results@weschool-demo.in")
    await generate_version(op, "Re-run for review (seed, not published)")
    logger.info("Phase 3 interview/result seed complete")
