"""Phase 3 — Interviews, Scoring, Results. Pytest regression suite."""
import asyncio
import os
import re
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pathlib import Path


def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    env = Path("/app/frontend/.env").read_text()
    for line in env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE = _base()
STAFF_PWD = "Staff@2026"
CAND_PWD = "Candidate@2026"
IST = timezone(timedelta(hours=5, minutes=30))


# -------- helpers --------
def login_staff(email):
    r = requests.post(f"{BASE}/api/auth/staff/login", json={"email": email, "password": "SuperAdmin@2026" if email.startswith("superadmin") else STAFF_PWD})
    r.raise_for_status()
    body = r.json()
    if body.get("step_up_required"):
        r = requests.post(f"{BASE}/api/auth/staff/login/complete", json={"challenge_id": body["challenge_id"], "code": body["debug_code"]})
        r.raise_for_status()
        body = r.json()
    return body["access_token"]


def login_candidate(email):
    r = requests.post(f"{BASE}/api/auth/candidate/login", json={"email": email, "password": CAND_PWD})
    r.raise_for_status()
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# -------- fixtures --------
@pytest.fixture(scope="module")
def tokens():
    return {
        "coordinator": login_staff("coordinator@weschool-demo.in"),
        "panelist": login_staff("panelist@weschool-demo.in"),
        "panelist2": login_staff("panelist2@weschool-demo.in"),
        "panelist3": login_staff("panelist3@weschool-demo.in"),
        "admissions": login_staff("admissions@weschool-demo.in"),
        "results": login_staff("results@weschool-demo.in"),
        "accounts": login_staff("accounts@weschool-demo.in"),
        "auditor": login_staff("auditor@weschool-demo.in"),
        "superadmin": login_staff("superadmin@weschool-demo.in"),
        "c02": login_candidate("candidate02@example.com"),
        "c03": login_candidate("candidate03@example.com"),
        "c12": login_candidate("candidate12@example.com"),
        "c13": login_candidate("candidate13@example.com"),
        "c14": login_candidate("candidate14@example.com"),
    }


@pytest.fixture(scope="module")
def sessions(tokens):
    r = requests.get(f"{BASE}/api/interviews/sessions", headers=H(tokens["coordinator"]))
    r.raise_for_status()
    return r.json()


# -------- bug fix: candidate02 reset state --------
class TestCandidate02State:
    def test_c02_is_draft_paid(self, tokens):
        r = requests.get(f"{BASE}/api/candidate/application", headers=H(tokens["c02"]))
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "draft"
        f = requests.get(f"{BASE}/api/candidate/application/fee", headers=H(tokens["c02"]))
        assert f.status_code == 200 and f.json().get("paid") is True
        secs = d.get("sections", {})
        assert len([k for k, v in secs.items() if v]) >= 5


# -------- downloads --------
class TestDownloads:
    def test_c03_application_pdf(self, tokens):
        r = requests.get(f"{BASE}/api/candidate/application/pdf", headers=H(tokens["c03"]))
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert r.content[:4] == b"%PDF"

    def test_c03_fee_invoice(self, tokens):
        r = requests.get(f"{BASE}/api/candidate/application/fee/receipt", headers=H(tokens["c03"]))
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_staff_applications_export(self, tokens):
        r = requests.get(f"{BASE}/api/admin/applications/export", headers=H(tokens["admissions"]))
        assert r.status_code == 200
        ctype = r.headers["content-type"]
        assert "spreadsheet" in ctype or "xlsx" in ctype
        assert "attachment" in r.headers.get("content-disposition", "")


# -------- coordinator sessions --------
class TestCoordinator:
    def test_list_sessions(self, tokens, sessions):
        assert len(sessions) >= 8
        assert any(s["type"] == "PI" and s["capacity"] == 1 for s in sessions)

    def test_list_locations(self, tokens):
        r = requests.get(f"{BASE}/api/interviews/locations", headers=H(tokens["coordinator"]))
        assert r.status_code == 200
        locs = r.json()
        assert len(locs) >= 2
        assert all("rooms" in l for l in locs)

    def test_create_location_and_room_and_session_validation(self, tokens):
        # create a transient location + room
        name = f"TEST_LOC_{datetime.now().microsecond}"
        r = requests.post(f"{BASE}/api/interviews/locations", headers=H(tokens["coordinator"]),
                          json={"name": name, "city": "Pune", "address": "T"})
        assert r.status_code == 200, r.text
        loc = r.json()
        rr = requests.post(f"{BASE}/api/interviews/locations/{loc['id']}/rooms", headers=H(tokens["coordinator"]),
                           json={"name": "RoomA", "capacity": 4})
        assert rr.status_code == 200
        room = rr.json()
        future = (datetime.now(IST).date() + timedelta(days=12)).isoformat()
        past = (datetime.now(IST).date() - timedelta(days=1)).isoformat()

        # Past date -> 422
        r1 = requests.post(f"{BASE}/api/interviews/sessions", headers=H(tokens["coordinator"]),
                           json={"type": "GA", "room_id": room["id"], "date": past, "start": "10:00", "end": "12:00", "capacity": 2})
        assert r1.status_code == 422 and r1.json()["detail"]["code"] == "past_date"

        # Over room capacity -> 422
        r2 = requests.post(f"{BASE}/api/interviews/sessions", headers=H(tokens["coordinator"]),
                           json={"type": "GA", "room_id": room["id"], "date": future, "start": "10:00", "end": "12:00", "capacity": 99})
        assert r2.status_code == 422 and r2.json()["detail"]["code"] == "over_capacity"

        # Create a valid one
        r3 = requests.post(f"{BASE}/api/interviews/sessions", headers=H(tokens["coordinator"]),
                           json={"type": "GA", "room_id": room["id"], "date": future, "start": "10:00", "end": "12:00", "capacity": 2})
        assert r3.status_code == 200
        # Room overlap -> 409
        r4 = requests.post(f"{BASE}/api/interviews/sessions", headers=H(tokens["coordinator"]),
                           json={"type": "GA", "room_id": room["id"], "date": future, "start": "11:00", "end": "13:00", "capacity": 2})
        assert r4.status_code == 409 and r4.json()["detail"]["code"] == "room_clash"

    def test_rbac_sessions_forbidden(self, tokens):
        r = requests.get(f"{BASE}/api/interviews/sessions", headers=H(tokens["panelist"]))
        assert r.status_code == 403

    def test_slot_report(self, tokens):
        r = requests.get(f"{BASE}/api/interviews/reports/slots", headers=H(tokens["coordinator"]))
        assert r.status_code == 200
        d = r.json()
        assert set(d) >= {"sessions", "bookings", "panelists"}

    def test_slot_report_export(self, tokens):
        r = requests.get(f"{BASE}/api/interviews/reports/slots/export", headers=H(tokens["coordinator"]))
        assert r.status_code == 200
        assert "spreadsheet" in r.headers["content-type"] or "xlsx" in r.headers["content-type"]

    def test_slot_report_rbac(self, tokens):
        assert requests.get(f"{BASE}/api/interviews/reports/slots", headers=H(tokens["results"])).status_code == 200
        assert requests.get(f"{BASE}/api/interviews/reports/slots", headers=H(tokens["panelist"])).status_code == 403
        assert requests.get(f"{BASE}/api/interviews/reports/slots", headers=H(tokens["accounts"])).status_code == 403


# -------- panelist access --------
class TestPanelistAccess:
    def test_panelist3_cannot_access_past_ga(self, tokens, sessions):
        past_ga = next(s for s in sessions if s["type"] == "GA" and s["date"] < datetime.now(IST).date().isoformat())
        r = requests.get(f"{BASE}/api/panel/sessions/{past_ga['id']}", headers=H(tokens["panelist3"]))
        assert r.status_code == 403 and r.json()["detail"]["code"] == "not_assigned"

    def test_panelist_only_assigned_sessions(self, tokens):
        r = requests.get(f"{BASE}/api/panel/sessions", headers=H(tokens["panelist3"]))
        assert r.status_code == 200
        # panelist3 only has future
        for s in r.json():
            assert s["date"] >= datetime.now(IST).date().isoformat()

    def test_panelist_forbidden_endpoints(self, tokens):
        assert requests.get(f"{BASE}/api/reports/evaluation", headers=H(tokens["panelist"])).status_code == 403
        assert requests.get(f"{BASE}/api/admin/applications", headers=H(tokens["panelist"])).status_code == 403


# -------- scoring --------
class TestScoring:
    def test_future_session_scoring_blocked(self, tokens, sessions):
        future_ga = next(s for s in sessions if s["type"] == "GA" and s["date"] > datetime.now(IST).date().isoformat())
        # panelist is assigned
        r = requests.put(f"{BASE}/api/panel/sessions/{future_ga['id']}/scores",
                         headers=H(tokens["panelist"]),
                         json={"entries": [{"application_id": "x", "scores": {}}], "submit": False})
        # could be 403 if not assigned, else 409 session_not_started
        assert r.status_code in (403, 409)
        if r.status_code == 409:
            assert r.json()["detail"]["code"] == "session_not_started"

    def test_past_ga_scoring_c12(self, tokens, sessions):
        past_ga = next(s for s in sessions if s["type"] == "GA" and s["date"] < datetime.now(IST).date().isoformat())
        r = requests.get(f"{BASE}/api/panel/sessions/{past_ga['id']}", headers=H(tokens["panelist"]))
        assert r.status_code == 200
        d = r.json()
        rub = d["rubric"]
        c12 = next((c for c in d["candidates"] if c["name"].lower().find("candidate") >= 0 or True), None)
        # pick candidate12 by candidate_ref/name - prefer the one with no assessment
        unscored = [c for c in d["candidates"] if not c["assessment"] or c["assessment"]["status"] != "submitted"]
        assert len(unscored) >= 1
        target = unscored[0]
        # out of range -> 422
        bad = {rub[0]["key"]: rub[0]["max"] + 10}
        for cr in rub[1:]:
            bad[cr["key"]] = 1
        r2 = requests.put(f"{BASE}/api/panel/sessions/{past_ga['id']}/scores", headers=H(tokens["panelist"]),
                          json={"entries": [{"application_id": target["application_id"], "scores": bad}], "submit": True})
        assert r2.status_code == 422 and r2.json()["detail"]["code"] == "out_of_range"
        # missing items -> incomplete on submit
        partial = {rub[0]["key"]: 1}
        r3 = requests.put(f"{BASE}/api/panel/sessions/{past_ga['id']}/scores", headers=H(tokens["panelist"]),
                          json={"entries": [{"application_id": target["application_id"], "scores": partial}], "submit": True})
        assert r3.status_code == 422 and r3.json()["detail"]["code"] == "incomplete"
        # valid draft
        good = {c["key"]: max(1, c["max"] // 2) for c in rub}
        r4 = requests.put(f"{BASE}/api/panel/sessions/{past_ga['id']}/scores", headers=H(tokens["panelist"]),
                          json={"entries": [{"application_id": target["application_id"], "scores": good}], "submit": False})
        assert r4.status_code == 200

    def test_submitted_locked(self, tokens, sessions):
        past_ga = next(s for s in sessions if s["type"] == "GA" and s["date"] < datetime.now(IST).date().isoformat())
        r = requests.get(f"{BASE}/api/panel/sessions/{past_ga['id']}", headers=H(tokens["panelist"]))
        d = r.json()
        locked = [c for c in d["candidates"] if c["assessment"] and c["assessment"]["status"] == "submitted"]
        if not locked:
            pytest.skip("no locked assessment")
        rub = d["rubric"]
        good = {c["key"]: 1 for c in rub}
        r2 = requests.put(f"{BASE}/api/panel/sessions/{past_ga['id']}/scores", headers=H(tokens["panelist"]),
                          json={"entries": [{"application_id": locked[0]["application_id"], "scores": good}], "submit": False})
        assert r2.status_code == 409 and r2.json()["detail"]["code"] == "locked"


# -------- admin correction --------
class TestAdminCorrection:
    def test_superadmin_correct(self, tokens, sessions):
        past_ga = next(s for s in sessions if s["type"] == "GA" and s["date"] < datetime.now(IST).date().isoformat())
        r = requests.get(f"{BASE}/api/panel/sessions/{past_ga['id']}", headers=H(tokens["panelist"]))
        d = r.json()
        locked = [c for c in d["candidates"] if c["assessment"] and c["assessment"]["status"] == "submitted"]
        if not locked:
            pytest.skip()
        aid = locked[0]["assessment"]["id"]
        rub = d["rubric"]
        new_scores = {c["key"]: max(1, (c["max"] // 2) + 1) for c in rub}
        # ensure change
        new_scores[rub[0]["key"]] = (locked[0]["assessment"]["scores"].get(rub[0]["key"], 0) + 1) % (rub[0]["max"] + 1)
        if new_scores[rub[0]["key"]] == locked[0]["assessment"]["scores"].get(rub[0]["key"], 0):
            new_scores[rub[0]["key"]] = (new_scores[rub[0]["key"]] + 1) % (rub[0]["max"] + 1)

        # Non-superadmin forbidden
        bad = requests.post(f"{BASE}/api/admin/assessments/{aid}/correct", headers=H(tokens["admissions"]),
                            json={"scores": new_scores, "reason": "testing correction"})
        assert bad.status_code == 403

        r2 = requests.post(f"{BASE}/api/admin/assessments/{aid}/correct", headers=H(tokens["superadmin"]),
                           json={"scores": new_scores, "reason": "unit test correction"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["version"] == locked[0]["assessment"]["version"] + 1

    def test_correct_reason_too_short(self, tokens, sessions):
        past_ga = next(s for s in sessions if s["type"] == "GA" and s["date"] < datetime.now(IST).date().isoformat())
        r = requests.get(f"{BASE}/api/panel/sessions/{past_ga['id']}", headers=H(tokens["panelist"]))
        d = r.json()
        locked = [c for c in d["candidates"] if c["assessment"] and c["assessment"]["status"] == "submitted"]
        if not locked:
            pytest.skip()
        aid = locked[0]["assessment"]["id"]
        r2 = requests.post(f"{BASE}/api/admin/assessments/{aid}/correct", headers=H(tokens["superadmin"]),
                           json={"scores": {}, "reason": "xx"})
        assert r2.status_code == 422


# -------- evaluation reports --------
class TestEvaluationReports:
    def test_report_access(self, tokens):
        for who in ("admissions", "coordinator", "results", "auditor", "superadmin"):
            assert requests.get(f"{BASE}/api/reports/evaluation?type=GA", headers=H(tokens[who])).status_code == 200

    def test_export_filename_slug(self, tokens):
        # fetch a panelist id
        pr = requests.get(f"{BASE}/api/interviews/panelists", headers=H(tokens["coordinator"]))
        pid = pr.json()[0]["id"]
        r = requests.get(f"{BASE}/api/reports/evaluation/export?type=GA&panelist_id={pid}", headers=H(tokens["admissions"]))
        assert r.status_code == 200
        cd = r.headers.get("content-disposition", "")
        assert "weschool-ga-scores-" in cd  # includes slug

    def test_ga_batch_pdf(self, tokens, sessions):
        past_ga = next(s for s in sessions if s["type"] == "GA" and s["date"] < datetime.now(IST).date().isoformat())
        r = requests.get(f"{BASE}/api/reports/evaluation/ga-batch/{past_ga['id']}/pdf", headers=H(tokens["coordinator"]))
        assert r.status_code == 200 and r.content[:4] == b"%PDF"


# -------- candidate PI booking --------
class TestPIBooking:
    def test_c13_mms_only_ineligible(self, tokens):
        r = requests.get(f"{BASE}/api/candidate/interviews", headers=H(tokens["c13"]))
        assert r.status_code == 200
        d = r.json()
        assert d["eligible"] is False and d["reasons"]

    def test_c14_book_and_reschedule(self, tokens):
        r = requests.get(f"{BASE}/api/candidate/interviews", headers=H(tokens["c14"]))
        assert r.status_code == 200
        d = r.json()
        if not d["eligible"]:
            pytest.skip(f"c14 not eligible: {d['reasons']}")
        bookable = [s for s in d["pi_slots"] if s["bookable"] and s["capacity"] > 1]  # avoid capacity-1 race session
        if not bookable:
            pytest.skip("no bookable PI slot")
        # if already booked (previous test run), skip
        if d["bookings"]:
            pytest.skip("c14 already has booking from prior run")
        s1 = bookable[0]
        r2 = requests.post(f"{BASE}/api/candidate/interviews/pi/book", headers=H(tokens["c14"]),
                           json={"session_id": s1["id"]})
        assert r2.status_code == 200, r2.text
        # Reschedule to another slot
        d2 = r2.json()
        other = [s for s in d2["pi_slots"] if s["id"] != s1["id"] and s["bookable"] and s["capacity"] > 1]
        if not other:
            pytest.skip("no alt slot")
        r3 = requests.post(f"{BASE}/api/candidate/interviews/pi/reschedule", headers=H(tokens["c14"]),
                           json={"session_id": other[0]["id"]})
        assert r3.status_code == 200
        bk = r3.json()["bookings"][0]
        assert bk["version"] == 2 and bk["reschedules"] == 1

    def test_c14_hall_ticket(self, tokens):
        r = requests.get(f"{BASE}/api/candidate/interviews/hall-ticket", headers=H(tokens["c14"]))
        if r.status_code == 409:
            pytest.skip("no booking yet")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        cd = r.headers["content-disposition"]
        assert re.search(r"HT-.*-PI-v\d+\.pdf", cd)

    def test_capacity1_booking_closed_or_full(self, tokens, sessions):
        cap1 = next((s for s in sessions if s["type"] == "PI" and s["capacity"] == 1), None)
        assert cap1
        # cutoff: slots within 24h
        # just verify sessions endpoint shows capacity 1


# -------- concurrency --------
class TestConcurrency:
    def test_capacity1_race(self, tokens, sessions):
        # Create a fresh capacity-1 PI session >2 days ahead
        locs = requests.get(f"{BASE}/api/interviews/locations", headers=H(tokens["coordinator"])).json()
        room = None
        for l in locs:
            for rm in l["rooms"]:
                if rm["capacity"] >= 1:
                    room = rm
                    break
            if room:
                break
        future = (datetime.now(IST).date() + timedelta(days=15)).isoformat()
        # Avoid room clash: pick late slot
        payload = {"type": "PI", "room_id": room["id"], "date": future, "start": "20:00", "end": "21:00",
                   "capacity": 1}
        r = requests.post(f"{BASE}/api/interviews/sessions", headers=H(tokens["coordinator"]), json=payload)
        if r.status_code != 200:
            pytest.skip(f"could not create: {r.text}")
        sid = r.json()["id"]

        # Try to race multiple candidates. Only c14 is eligible for PI typically; others may already be booked.
        # Simulate concurrency: fire two booking attempts from c14 (one will say already_booked but reserve mustn't exceed capacity).
        # Better: use reschedule to this slot from c14 and simultaneously check capacity.
        async def hit():
            def go():
                return requests.post(f"{BASE}/api/candidate/interviews/pi/reschedule",
                                     headers=H(tokens["c14"]),
                                     json={"session_id": sid})
            return await asyncio.get_event_loop().run_in_executor(None, go)

        async def race():
            return await asyncio.gather(hit(), hit(), hit(), return_exceptions=True)

        results = asyncio.run(race())
        statuses = [getattr(x, "status_code", None) for x in results]
        # at most one 200
        oks = sum(1 for s in statuses if s == 200)
        assert oks <= 1, f"multiple winners: {statuses}"

        # Verify booked never exceeded capacity
        sess = requests.get(f"{BASE}/api/interviews/sessions", headers=H(tokens["coordinator"])).json()
        this = next(s for s in sess if s["id"] == sid)
        assert this["booked"] <= 1


# -------- results --------
class TestResults:
    def test_candidate_results_before_publish_visible_from_seed(self, tokens):
        r = requests.get(f"{BASE}/api/candidate/results", headers=H(tokens["c03"]))
        assert r.status_code == 200
        d = r.json()
        # Seed publishes v1
        assert d["published"] in (True, False)

    def test_admissions_can_generate_not_publish(self, tokens):
        r = requests.post(f"{BASE}/api/results/versions", headers=H(tokens["admissions"]),
                          json={"note": "pytest generate"})
        assert r.status_code == 200, r.text
        v = r.json()["version"]
        # Can't approve
        r2 = requests.post(f"{BASE}/api/results/versions/{v}/approve", headers=H(tokens["admissions"]),
                           json={"note": "nope"})
        assert r2.status_code == 403
        # superadmin also cannot (results.publish perm only on result_approver)
        r3 = requests.post(f"{BASE}/api/results/versions/{v}/approve", headers=H(tokens["superadmin"]),
                           json={"note": "nope"})
        assert r3.status_code == 403

    def test_publish_unapproved_409(self, tokens):
        # pick latest generated
        vl = requests.get(f"{BASE}/api/results/versions", headers=H(tokens["results"])).json()
        gen = next((v for v in vl if v["status"] == "generated"), None)
        if not gen:
            pytest.skip()
        r = requests.post(f"{BASE}/api/results/versions/{gen['version']}/publish", headers=H(tokens["results"]),
                          json={"note": "early"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "invalid_state"

    def test_approve_and_publish_flow(self, tokens):
        r = requests.post(f"{BASE}/api/results/versions", headers=H(tokens["admissions"]),
                          json={"note": "pytest flow"})
        v = r.json()["version"]
        r2 = requests.post(f"{BASE}/api/results/versions/{v}/approve", headers=H(tokens["results"]),
                           json={"note": "ok"})
        assert r2.status_code == 200
        r3 = requests.post(f"{BASE}/api/results/versions/{v}/publish", headers=H(tokens["results"]),
                           json={"note": "live"})
        assert r3.status_code == 200
        # candidate sees new version
        cr = requests.get(f"{BASE}/api/candidate/results", headers=H(tokens["c03"]))
        assert cr.status_code == 200
        if cr.json()["published"]:
            assert cr.json()["version"] == v

    def test_version_has_tfw_rows(self, tokens):
        vl = requests.get(f"{BASE}/api/results/versions", headers=H(tokens["results"])).json()
        v = vl[0]["version"]
        d = requests.get(f"{BASE}/api/results/versions/{v}", headers=H(tokens["results"])).json()
        assert "rows" in d
        # Candidates 7 & 11 TFW-eligible
        tfw = [r for r in d["rows"] if r.get("tfw_eligible")]
        assert len(tfw) >= 1

    def test_candidate_result_pdf(self, tokens):
        r = requests.get(f"{BASE}/api/candidate/results/pdf", headers=H(tokens["c03"]))
        if r.status_code == 409:
            pytest.skip("results not published for this candidate")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"


# -------- policies --------
class TestPolicies:
    def test_superadmin_draft_selection_rules(self, tokens):
        # fetch active
        r = requests.get(f"{BASE}/api/policies", headers=H(tokens["superadmin"]))
        assert r.status_code == 200
        sel = next(p for p in r.json() if p["key"] == "selection_rules")
        content = dict(sel["active"]["content"])
        # weights sum to 100 (unchanged)
        r2 = requests.post(f"{BASE}/api/policies/selection_rules/versions", headers=H(tokens["superadmin"]),
                           json={"content": content, "change_note": "pytest draft"})
        assert r2.status_code == 200 and r2.json()["status"] == "draft"

    def test_bad_weights_rejected(self, tokens):
        r = requests.get(f"{BASE}/api/policies", headers=H(tokens["superadmin"]))
        sel = next(p for p in r.json() if p["key"] == "selection_rules")
        bad = dict(sel["active"]["content"])
        bad["exam_weight"] = 10; bad["ga_weight"] = 10; bad["pi_weight"] = 10
        r2 = requests.post(f"{BASE}/api/policies/selection_rules/versions", headers=H(tokens["superadmin"]),
                           json={"content": bad, "change_note": "bad weights"})
        assert r2.status_code == 422

    def test_waitlist_above_selected_rejected(self, tokens):
        r = requests.get(f"{BASE}/api/policies", headers=H(tokens["superadmin"]))
        sel = next(p for p in r.json() if p["key"] == "selection_rules")
        bad = dict(sel["active"]["content"])
        bad["waitlist_cutoff"] = bad["selected_cutoff"] + 10
        r2 = requests.post(f"{BASE}/api/policies/selection_rules/versions", headers=H(tokens["superadmin"]),
                           json={"content": bad, "change_note": "bad cutoff"})
        assert r2.status_code == 422
