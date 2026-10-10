import logging
from datetime import datetime, timedelta

from bson import ObjectId

from core import IST, db, now_utc
from routes.allotment import Allotment, Batch, ensure_seat, programs
from routes.partb import Consent, Eligibility, ImportBatch
from routes.partb_docs import PartBDoc, checklist
from services import storage
from services.notify import notify

logger = logging.getLogger(__name__)
# candidate index -> eligibility rows (program, outcome, merit_rank, waitlist_rank, choice)
FIXTURE = {
    3: [("PGDM-HC", "selected", 3, None, 1), ("PGDM-MUM", "waitlisted", None, 2, 2)],
    4: [("PGDM-ME", "waitlisted", None, 1, 1), ("PGDM-BLR", "selected", 1, None, 2)],
    7: [("PGDM-EB", "selected", 1, None, 1), ("PGDM-MUM", "waitlisted", None, 1, 3)],
    11: [("PGDM-ME", "selected", 2, None, 1)],
    13: [("MMS-ACAP", "selected", 1, None, 1)],
    14: [("PGDM-EB", "rejected", None, None, 1)],
    **{i: [("MMS-AGCAP", "selected", i - 14, None, 1)] for i in (15, 16, 17, 18)},
}
CONSENTED = (3, 4, 7, 11, 13, 15, 16, 17, 18)
DOCS = {3: "discrepancy", 4: "verified", 7: "verified", 11: "registered", 15: "verified", 16: "verified", 17: "verified", 18: "verified"}
MERIT = ["PGDM-BLR", "PGDM-EB", "PGDM-HC", "PGDM-ME", "MMS-ACAP", "MMS-AGCAP"]
WAIT = ["PGDM-ME", "PGDM-MUM"]


async def ensure_partb_indexes():
    await db.partb_eligibility.create_index([("candidate_id", 1), ("program_code", 1)], unique=True, name="elig_active_uniq",
                                            partialFilterExpression={"status": "active"})
    await db.partb_consents.create_index([("candidate_id", 1), ("kind", 1), ("batch_id", 1)], unique=True, name="better_uniq",
                                         partialFilterExpression={"kind": "betterment"})
    await db.partb_documents.create_index([("candidate_id", 1), ("stage", 1), ("doc_key", 1)], unique=True)
    await db.partb_allotments.create_index("candidate_id", unique=True, name="one_seat_per_candidate",
                                           partialFilterExpression={"seat_held": True})
    await db.partb_allotments.create_index("batch_id")
    await db.partb_seats.create_index([("cycle_id", 1), ("program_code", 1)], unique=True)
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])


def _pdf() -> bytes:
    body = b"BT /F1 12 Tf 72 720 Td (WeSchool seed document) Tj ET" + b" " * 1200
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj "
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj 4 0 obj<</Length "
            + str(len(body)).encode() + b">>stream\n" + body + b"\nendstream endobj\ntrailer<</Root 1 0 R>>\n%%EOF")


async def seed_partb():
    if await db.partb_import_batches.find_one({}):
        return
    cycle = await db.cycles.find_one({"code": "2026-28"})
    if not cycle:
        return
    cid = str(cycle["_id"])
    users, apps = {}, {}
    for i in FIXTURE:
        u = await db.users.find_one({"email": f"candidate{i:02d}@example.com"})
        a = await db.applications.find_one({"candidate_id": str(u["_id"]), "status": "submitted"}) if u else None
        if not a:
            logger.warning(f"seed_partb skipped: candidate{i:02d} has no submitted application")
            return
        users[i], apps[i] = str(u["_id"]), a
    now = now_utc()
    batch = ImportBatch(cycle_id=cid, kind="file", filename="seed-fixture.csv", checksum="seed-fixture-v1", mode="insert", status="inserted",
                        rows_total=sum(len(v) for v in FIXTURE.values()), rows_valid=sum(len(v) for v in FIXTURE.values()),
                        created_by="seed", committed_at=now, committed_by="seed")
    bid = str((await db.partb_import_batches.insert_one(batch.to_mongo())).inserted_id)
    for i, rows in FIXTURE.items():
        for code, out, mr, wr, ch in rows:
            await db.partb_eligibility.insert_one(Eligibility(cycle_id=cid, candidate_id=users[i], application_id=str(apps[i]["_id"]),
                                                              application_ref=apps[i]["application_ref"], program_code=code, outcome=out,
                                                              merit_rank=mr, waitlist_rank=wr, choice_position=ch, import_id=bid).to_mongo())
        await db.partb_import_batches.update_one({"_id": ObjectId(bid)}, {"$inc": {"inserted": len(rows)}})
    progs = await programs()
    for code, p in progs.items():
        await ensure_seat(cid, code, p["seat_capacity"])
    await db.partb_seats.update_one({"cycle_id": cid, "program_code": "MMS-AGCAP"}, {"$set": {"capacity": 1}})

    d0 = datetime.now(IST).date()
    batches = {}
    for kind, codes, start, end in (("merit", MERIT, -3, 14), ("waitlist", WAIT, -1, 10)):
        for code in codes:
            b = Batch(cycle_id=cid, kind=kind, name=f"{'Merit round 1' if kind == 'merit' else 'Waiting list 1'} · {code}", program_code=code,
                      start_date=(d0 + timedelta(days=start)).isoformat(), end_date=(d0 + timedelta(days=end)).isoformat(), created_by="seed")
            batches[(kind, code)] = str((await db.partb_batches.insert_one(b.to_mongo())).inserted_id)

    for i in CONSENTED:
        courses = {code: "accept" for code, out, *_ in FIXTURE[i] if out != "rejected"}
        await db.partb_consents.insert_one(Consent(cycle_id=cid, candidate_id=users[i], courses=courses, overall=True, actor="seed").to_mongo())

    try:
        stored = await storage.put_object(f"{storage.APP_NAME}/partb/seed/sample-document.pdf", _pdf(), "application/pdf")
    except Exception as e:
        logger.warning(f"seed_partb: document upload skipped ({e})")
        stored = None
    if stored:
        for i, state in DOCS.items():
            items = await checklist(users[i], "initial")
            for n, it in enumerate(items):
                fid = str((await db.files.insert_one({"owner_id": users[i], "kind": "partb_doc", "storage_path": stored["path"],
                                                      "content_type": "application/pdf", "size": 1500, "original_filename": f"{it['key']}.pdf",
                                                      "is_deleted": False, "created_at": now})).inserted_id)
                st = "discrepancy" if state == "discrepancy" and n == 1 else ("registered" if state in ("registered", "discrepancy") else "verified")
                remarks = "Scan is unreadable and the seal is cut off. Upload a clear, complete copy." if st == "discrepancy" else None
                hist = [{"action": "uploaded", "version": 1, "by": "seed", "at": now}]
                if st != "registered":
                    hist.append({"action": st, "version": 1, "remarks": remarks, "by": "verifier@weschool-demo.in", "at": now})
                await db.partb_documents.insert_one(PartBDoc(candidate_id=users[i], stage="initial", doc_key=it["key"], label=it["label"],
                                                             file_id=fid, content_type="application/pdf", status=st, remarks=remarks, history=hist,
                                                             reviewed_by="verifier@weschool-demo.in" if st != "registered" else None,
                                                             reviewed_at=now if st != "registered" else None).to_mongo())
            if state == "discrepancy":
                await notify(users[i], "discrepancy", f"Re-upload needed: {items[1]['label']}",
                             "Reviewer remark: Scan is unreadable and the seal is cut off. Upload a clear, complete copy.")

    for i, code, status in ((4, "PGDM-BLR", "allotted"), (7, "PGDM-EB", "on_hold")):
        a = Allotment(cycle_id=cid, candidate_id=users[i], application_ref=apps[i]["application_ref"], program_code=code,
                      batch_id=batches[("merit", code)], batch_kind="merit", status=status, seat_held=True,
                      receipt_version=1 if status == "allotted" else 0, created_by="admissions@weschool-demo.in",
                      history=[{"action": status, "by": "admissions@weschool-demo.in", "at": now, "version": 1}])
        aid = str((await db.partb_allotments.insert_one(a.to_mongo())).inserted_id)
        await db.partb_seats.update_one({"cycle_id": cid, "program_code": code}, {"$inc": {"filled": 1}})
        await db.seat_events.insert_one({"program_code": code, "delta": 1, "reason": "seed allotment", "allotment_id": aid, "at": now})
        await notify(users[i], "allotment", f"Seat {status.replace('_', ' ')}: {progs[code]['name']}",
                     f"You have a seat ({status.replace('_', ' ')}) in {progs[code]['name']} via Merit round 1.")
    for i in FIXTURE:
        if i != 14:
            await notify(users[i], "partb_open", "Part B is open for you", "Your merit/waitlist status is available. Review it and give your consent.")
    logger.info("Phase 4 Part B seed complete")
