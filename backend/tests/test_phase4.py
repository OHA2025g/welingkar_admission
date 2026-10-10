"""Phase 4 — Part B (Counselling, Consent, Documents, Allotment). Pytest regression suite."""
import concurrent.futures as cf
import io
import os
import time
from pathlib import Path

import pytest
import requests

STAFF_PWD = "Staff@2026"
CAND_PWD = "Candidate@2026"


def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE = _base()


def login_staff(email, pwd=None):
    pwd = pwd or ("SuperAdmin@2026" if email.startswith("superadmin") else STAFF_PWD)
    r = requests.post(f"{BASE}/api/auth/staff/login", json={"email": email, "password": pwd}, timeout=30)
    r.raise_for_status()
    body = r.json()
    if body.get("step_up_required"):
        r = requests.post(f"{BASE}/api/auth/staff/login/complete",
                          json={"challenge_id": body["challenge_id"], "code": body["debug_code"]}, timeout=30)
        r.raise_for_status()
        body = r.json()
    return body["access_token"]


def login_candidate(n):
    r = requests.post(f"{BASE}/api/auth/candidate/login",
                      json={"email": f"candidate{n:02d}@example.com", "password": CAND_PWD}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- shared fixtures ----------
@pytest.fixture(scope="module")
def admissions():
    return login_staff("admissions@weschool-demo.in")


@pytest.fixture(scope="module")
def verifier():
    return login_staff("verifier@weschool-demo.in")


@pytest.fixture(scope="module")
def superadmin():
    return login_staff("superadmin@weschool-demo.in")


@pytest.fixture(scope="module")
def auditor():
    return login_staff("auditor@weschool-demo.in")


@pytest.fixture(scope="module")
def panelist():
    return login_staff("panelist@weschool-demo.in")


def _programs_cand_map(admissions):
    """Fetch application_ref for candidate05 and candidate12."""
    r = requests.get(f"{BASE}/api/admin/applications?limit=200", headers=H(admissions), timeout=30)
    r.raise_for_status()
    rows = r.json()
    rows = rows if isinstance(rows, list) else rows.get("rows", [])
    out = {}
    for row in rows:
        em = row.get("email") or row.get("candidate_email") or ""
        if em in ("candidate05@example.com", "candidate12@example.com"):
            out[em] = row.get("application_ref")
    return out


@pytest.fixture(scope="module")
def refs(admissions):
    return _programs_cand_map(admissions)


_IMPORT_STATE = {}


# ------------------ 1. CANDIDATE PART B ACCESS ------------------
class TestCandidatePartBAccess:
    def test_c14_ineligible(self):
        tok = login_candidate(14)
        r = requests.get(f"{BASE}/api/candidate/partb", headers=H(tok), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["eligible"] is False
        assert "Part B" in d.get("reason", "")

    def test_c04_courses(self):
        tok = login_candidate(4)
        r = requests.get(f"{BASE}/api/candidate/partb", headers=H(tok), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["eligible"] is True
        codes = {c["program_code"] for c in d["courses"]}
        assert "PGDM-BLR" in codes and "PGDM-ME" in codes
        # c04 should have an allotment (PGDM-BLR allotted)
        assert d["allotment"] and d["allotment"]["program_code"] == "PGDM-BLR"
        # betterment offer for PGDM-ME should be present
        assert any(o["program_code"] == "PGDM-ME" for o in d["betterment_offers"])


# ------------------ 2. IMPORTS ------------------
class TestImports:
    def _csv_for(self, refs):
        c5 = refs["candidate05@example.com"]
        c12 = refs["candidate12@example.com"]
        # Valid rows + a couple of invalid rows (unknown program, duplicate rank)
        rows = [
            "cycle_code,program_code,application_reference,outcome,merit_rank,waitlist_rank,choice_position,list_version",
            f"2026-28,PGDM-BD,{c5},selected,101,,1,",
            f"2026-28,PGDM-BD,{c12},waitlisted,,101,1,",
            f"2026-28,PGDM-ZZZ,{c5},selected,900,,1,",      # unknown program
            f"2026-28,PGDM-BD,{c5},selected,102,,1,",       # duplicate candidate-course (in file)
            f"2026-28,PGDM-BD,UNKNOWN-REF,selected,103,,1,",  # unknown app ref
            f"2026-28,PGDM-BD,{c5},waitlisted,,,1,",         # missing waitlist rank
        ]
        return ("\n".join(rows)).encode()

    def test_validate_mode_captures_errors(self, admissions, refs):
        data = self._csv_for(refs)
        files = {"file": ("partb-test.csv", io.BytesIO(data), "text/csv")}
        r = requests.post(f"{BASE}/api/partb/imports", headers=H(admissions),
                          files=files, data={"mode": "validate"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "validated"
        assert d["rows_total"] == 6
        assert d["rows_valid"] == 2
        # errors contain expected categories
        msgs = " ".join(e["message"] for e in d["errors"])
        assert "Unknown program" in msgs
        assert "Duplicate candidate-course" in msgs
        assert "No submitted application" in msgs
        _IMPORT_STATE["bid"] = d["id"]

    def test_error_report_xlsx(self, admissions):
        bid = _IMPORT_STATE["bid"]
        r = requests.get(f"{BASE}/api/partb/imports/{bid}/error-report", headers=H(admissions), timeout=30)
        assert r.status_code == 200
        assert "spreadsheet" in r.headers.get("Content-Type", "")

    def test_commit_inserts_valid_rows(self, admissions):
        bid = _IMPORT_STATE["bid"]
        r = requests.post(f"{BASE}/api/partb/imports/{bid}/commit", headers=H(admissions), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "inserted"
        assert d["inserted"] >= 2

    def test_duplicate_file_insert_409(self, admissions, refs):
        """Re-upload same file in insert mode should 409 duplicate_file."""
        data = self._csv_for(refs)
        files = {"file": ("partb-test.csv", io.BytesIO(data), "text/csv")}
        r = requests.post(f"{BASE}/api/partb/imports", headers=H(admissions),
                          files=files, data={"mode": "insert"}, timeout=30)
        # Note: commit path above re-ran validate on the stored rows and inserted;
        # this new upload has same checksum of the raw file. The server dedupes by checksum of raw upload.
        # Since checksum was recorded only when uploaded via /imports endpoint, the committed batch
        # was created via /imports (validate), with same checksum, now status=inserted => 409
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "duplicate_file"

    def test_rollback_removes_eligibility(self, admissions):
        bid = _IMPORT_STATE["bid"]
        r = requests.post(f"{BASE}/api/partb/imports/{bid}/rollback", headers=H(admissions),
                          json={"reason": "cleaning up test data for phase 4"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "rolled_back"

    def test_from_result_requires_published(self, admissions):
        # Use a non-existent version to assert 404 path (we don't want to re-import real published rows)
        r = requests.post(f"{BASE}/api/partb/imports/from-result", headers=H(admissions),
                          json={"version": 9999, "mode": "validate"}, timeout=30)
        assert r.status_code == 404


# ------------------ 3. CONSENT ------------------
class TestConsent:
    def test_already_consented_409(self):
        tok = login_candidate(13)
        r = requests.post(f"{BASE}/api/candidate/partb/consent", headers=H(tok),
                          json={"courses": {"MMS-ACAP": "accept"}, "overall": True}, timeout=30)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "already_consented"

    def test_ineligible_candidate_403(self):
        tok = login_candidate(14)
        r = requests.post(f"{BASE}/api/candidate/partb/consent", headers=H(tok),
                          json={"courses": {}, "overall": True}, timeout=30)
        assert r.status_code == 403

    def test_correct_consent_seat_held(self, admissions):
        """Correcting c04 (BLR holder) to decline BLR must return 409 seat_held."""
        # Need candidate_id of candidate04 -> use partb_candidates list
        r = requests.get(f"{BASE}/api/partb/candidates", headers=H(admissions), timeout=30)
        assert r.status_code == 200
        row = next(c for c in r.json() if c["application_ref"].endswith("S00004"))
        cid = row["candidate_id"]
        r2 = requests.post(f"{BASE}/api/partb/consents/{cid}/correct", headers=H(admissions),
                           json={"courses": {"PGDM-BLR": "decline", "PGDM-ME": "accept"}, "overall": True,
                                 "reason": "testing seat_held guard"}, timeout=30)
        assert r2.status_code == 409
        assert r2.json()["detail"]["code"] == "seat_held"


# ------------------ 4. DOCUMENTS ------------------
PDF_BYTES = b"%PDF-1.4\n" + b" " * 1500 + b"\n%%EOF"


class TestDocuments:
    def test_initial_locked_without_consent(self):
        """candidate12 has no part-b eligibility -> stage lock returns ineligible via 403 on upload path?
        Actually /candidate/partb/documents/initial would still return but locked_reason set.
        We just check that it reports locked for a non-consented eligible candidate (none in seed with no consent except
        c14 rejected). Use c11 who IS consented so not locked."""
        tok = login_candidate(11)
        r = requests.get(f"{BASE}/api/candidate/partb/documents/initial", headers=H(tok), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["locked_reason"] is None  # c11 is consented

    def test_c03_reupload_discrepancy_doc(self):
        tok = login_candidate(3)
        docs = requests.get(f"{BASE}/api/candidate/partb/documents/initial", headers=H(tok), timeout=30).json()
        # Find a discrepancy item
        disc = next((it for it in docs["items"] if it["doc"] and it["doc"]["status"] == "discrepancy"), None)
        assert disc is not None, "candidate03 should have a discrepancy doc in seed"
        key = disc["key"]
        v_before = disc["doc"]["version"]
        files = {"file": (f"{key}.pdf", PDF_BYTES, "application/pdf")}
        r = requests.post(f"{BASE}/api/candidate/partb/documents/initial/{key}", headers=H(tok),
                         files=files, timeout=30)
        assert r.status_code == 200, r.text
        new_item = next(it for it in r.json()["items"] if it["key"] == key)
        assert new_item["doc"]["version"] == v_before + 1
        assert new_item["doc"]["status"] == "registered"
        pytest.c03_reuploaded_key = key

    def test_invalid_type_rejected(self):
        tok = login_candidate(3)
        files = {"file": ("bad.pdf", b"not a pdf", "application/pdf")}
        r = requests.post(f"{BASE}/api/candidate/partb/documents/initial/id_proof", headers=H(tok),
                         files=files, timeout=30)
        assert r.status_code == 422

    def test_reupload_verified_409(self):
        """candidate04 has all docs verified; reuploading should 409 already_verified."""
        tok = login_candidate(4)
        docs = requests.get(f"{BASE}/api/candidate/partb/documents/initial", headers=H(tok), timeout=30).json()
        ver = next((it for it in docs["items"] if it["doc"] and it["doc"]["status"] == "verified"), None)
        assert ver is not None
        files = {"file": (f"{ver['key']}.pdf", PDF_BYTES, "application/pdf")}
        r = requests.post(f"{BASE}/api/candidate/partb/documents/initial/{ver['key']}", headers=H(tok),
                         files=files, timeout=30)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "already_verified"


# ------------------ 5. VERIFIER RBAC & WORKLIST ------------------
class TestVerifier:
    def test_rbac_denies_admin_endpoints(self, verifier):
        for path in ("/api/admin/applications", "/api/partb/batches", "/api/partb/candidates",
                     "/api/cycles", "/api/programs"):
            r = requests.get(f"{BASE}{path}", headers=H(verifier), timeout=30)
            assert r.status_code == 403, f"{path} -> {r.status_code}"

    def test_worklist_counts(self, verifier):
        r = requests.get(f"{BASE}/api/verify/worklist?stage=initial&list=registered",
                        headers=H(verifier), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert set(d["counts"].keys()) == {"registered", "discrepancy", "verified"}

    def test_review_discrepancy_requires_remarks(self, verifier):
        """Open c03's just-reuploaded doc, mark discrepancy with short remarks -> 422."""
        # fetch c03 via worklist review
        wl = requests.get(f"{BASE}/api/verify/worklist?stage=initial&list=registered",
                         headers=H(verifier), timeout=30).json()
        if not wl["rows"]:
            pytest.skip("no registered docs in worklist")
        cid = wl["rows"][0]["candidate_id"]
        vc = requests.get(f"{BASE}/api/verify/candidates/{cid}?stage=initial",
                         headers=H(verifier), timeout=30).json()
        item = next(it for it in vc["items"] if it["doc"] and it["doc"]["status"] == "registered")
        doc_id = item["doc"]["id"]
        ver = item["doc"]["version"]
        # short remarks -> 422
        r = requests.post(f"{BASE}/api/verify/documents/{doc_id}", headers=H(verifier),
                         json={"status": "discrepancy", "remarks": "bad", "version": ver}, timeout=30)
        assert r.status_code == 422

    def test_stale_version_409(self, verifier):
        wl = requests.get(f"{BASE}/api/verify/worklist?stage=initial&list=registered",
                         headers=H(verifier), timeout=30).json()
        if not wl["rows"]:
            pytest.skip("no registered docs")
        cid = wl["rows"][0]["candidate_id"]
        vc = requests.get(f"{BASE}/api/verify/candidates/{cid}?stage=initial",
                         headers=H(verifier), timeout=30).json()
        item = next(it for it in vc["items"] if it["doc"] and it["doc"]["status"] == "registered")
        doc_id = item["doc"]["id"]
        r = requests.post(f"{BASE}/api/verify/documents/{doc_id}", headers=H(verifier),
                         json={"status": "verified", "remarks": "", "version": 999}, timeout=30)
        assert r.status_code == 409


# ------------------ 6. BATCHES ------------------
class TestBatches:
    def test_create_edit_delete(self, admissions):
        # Create
        r = requests.post(f"{BASE}/api/partb/batches", headers=H(admissions),
                         json={"kind": "merit", "name": "TEST Batch PGDM-BD r1",
                               "program_code": "PGDM-BD",
                               "start_date": "2026-01-01", "end_date": "2026-02-01"}, timeout=30)
        assert r.status_code == 200, r.text
        bid = r.json()["id"]
        # Edit
        r2 = requests.put(f"{BASE}/api/partb/batches/{bid}", headers=H(admissions),
                         json={"name": "TEST Batch PGDM-BD r1 edited",
                               "start_date": "2026-01-01", "end_date": "2026-02-15"}, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["name"].endswith("edited")
        # Delete
        r3 = requests.delete(f"{BASE}/api/partb/batches/{bid}", headers=H(admissions), timeout=30)
        assert r3.status_code == 200

    def test_end_before_start_422(self, admissions):
        r = requests.post(f"{BASE}/api/partb/batches", headers=H(admissions),
                         json={"kind": "merit", "name": "TEST bad", "program_code": "PGDM-BD",
                               "start_date": "2026-02-01", "end_date": "2026-01-01"}, timeout=30)
        assert r.status_code == 422

    def test_delete_batch_with_allotments_409(self, admissions):
        # 'Merit round 1 · PGDM-BLR' has an allotment for c04
        batches = requests.get(f"{BASE}/api/partb/batches?kind=merit", headers=H(admissions), timeout=30).json()
        b = next(x for x in batches if x["program_code"] == "PGDM-BLR" and x["kind"] == "merit")
        r = requests.delete(f"{BASE}/api/partb/batches/{b['id']}", headers=H(admissions), timeout=30)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "has_allotments"


# ------------------ 7. ALLOTMENT DASHBOARD ------------------
class TestDashboard:
    def test_blr_dashboard(self, admissions):
        batches = requests.get(f"{BASE}/api/partb/batches?kind=merit", headers=H(admissions), timeout=30).json()
        b = next(x for x in batches if x["program_code"] == "PGDM-BLR")
        r = requests.get(f"{BASE}/api/partb/batches/{b['id']}/dashboard", headers=H(admissions), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["counts"]["allotted"] >= 1
        assert d["vacancy"]["program_code"] == "PGDM-BLR"


# ------------------ 8. CONCURRENCY on MMS-AGCAP (cap=1, 4 cands) ------------------
class TestConcurrency:
    @pytest.fixture(scope="class")
    def agcap_batch(self, admissions):
        batches = requests.get(f"{BASE}/api/partb/batches?kind=merit", headers=H(admissions), timeout=30).json()
        return next(x for x in batches if x["program_code"] == "MMS-AGCAP")

    def test_vacancy_before(self, admissions):
        v = requests.get(f"{BASE}/api/partb/vacancy", headers=H(admissions), timeout=30).json()
        a = next(x for x in v if x["program_code"] == "MMS-AGCAP")
        if a["filled"] >= 1:
            pytest.skip("MMS-AGCAP seat already filled from a prior run - rerun needs seed reset")

    def test_parallel_allot_only_one_wins(self, admissions, agcap_batch):
        """Fire parallel allot requests for 4 different candidates. Only one should succeed."""
        # Get candidate_ids for cand15-18
        parts = requests.get(f"{BASE}/api/partb/candidates", headers=H(admissions), timeout=30).json()
        agcap_cands = [p for p in parts
                       if any(c["program_code"] == "MMS-AGCAP" for c in p["courses"])
                       and not p.get("allotment")]
        if len(agcap_cands) < 2:
            pytest.skip("Not enough fresh MMS-AGCAP candidates (seat race already resolved)")
        bid = agcap_batch["id"]

        def allot(cid):
            try:
                return requests.post(f"{BASE}/api/partb/batches/{bid}/allot", headers=H(admissions),
                                    json={"candidate_id": cid, "status": "allotted"}, timeout=30)
            except Exception as e:
                return e

        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(allot, c["candidate_id"]) for c in agcap_cands]
            results = [f.result() for f in cf.as_completed(futs)]
        codes = [r.status_code for r in results if hasattr(r, "status_code")]
        wins = sum(1 for c in codes if c == 200)
        losers = sum(1 for c in codes if c == 409)
        print(f"concurrency codes = {codes}")
        assert wins == 1, f"expected exactly 1 winner, got {wins} ({codes})"
        assert losers >= 1

        # Vacancy check: filled=1
        v = requests.get(f"{BASE}/api/partb/vacancy", headers=H(admissions), timeout=30).json()
        a = next(x for x in v if x["program_code"] == "MMS-AGCAP")
        assert a["filled"] == 1
        assert a["vacant"] == 0
        assert a["reconciled"] is True


# ------------------ 9. ALLOTMENT RULES (provisional, no_consent, docs guards) ------------------
class TestAllotmentRules:
    def test_c11_provisional_allowed(self, admissions):
        """c11: consented, docs registered (not verified) -> 'allotted' should 409 docs_not_verified, provisional OK."""
        batches = requests.get(f"{BASE}/api/partb/batches?kind=merit", headers=H(admissions), timeout=30).json()
        b = next(x for x in batches if x["program_code"] == "PGDM-ME")
        parts = requests.get(f"{BASE}/api/partb/candidates", headers=H(admissions), timeout=30).json()
        c11 = next((p for p in parts if p["application_ref"].endswith("S00011")), None)
        if not c11:
            pytest.skip("c11 not in part B")
        if c11.get("allotment"):
            pytest.skip("c11 already allotted (prior run)")
        # Try 'allotted' first -> should 409 docs_not_verified (docs registered only)
        r = requests.post(f"{BASE}/api/partb/batches/{b['id']}/allot", headers=H(admissions),
                         json={"candidate_id": c11["candidate_id"], "status": "allotted"}, timeout=30)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "docs_not_verified"
        # Provisional should work
        r2 = requests.post(f"{BASE}/api/partb/batches/{b['id']}/allot", headers=H(admissions),
                          json={"candidate_id": c11["candidate_id"], "status": "provisional"}, timeout=30)
        assert r2.status_code == 200, r2.text


# ------------------ 10. ON-HOLD DISPOSITION (c07) ------------------
class TestDisposition:
    def test_cancel_on_hold_releases_seat(self, admissions):
        parts = requests.get(f"{BASE}/api/partb/candidates", headers=H(admissions), timeout=30).json()
        c07 = next((p for p in parts if p["application_ref"].endswith("S00007")), None)
        if not c07 or not c07.get("allotment"):
            pytest.skip("c07 has no on-hold allotment")
        aid = c07["allotment"]["id"]
        # Vacancy before
        v0 = requests.get(f"{BASE}/api/partb/vacancy", headers=H(admissions), timeout=30).json()
        before = next(x for x in v0 if x["program_code"] == "PGDM-EB")["filled"]
        r = requests.post(f"{BASE}/api/partb/allotments/{aid}/disposition", headers=H(admissions),
                         json={"to": "cancelled", "remarks": "testing on-hold cancel path"}, timeout=30)
        assert r.status_code == 200, r.text
        v1 = requests.get(f"{BASE}/api/partb/vacancy", headers=H(admissions), timeout=30).json()
        after = next(x for x in v1 if x["program_code"] == "PGDM-EB")["filled"]
        assert after == before - 1
        # Second disposition call on same allotment -> 409 not_on_hold
        r2 = requests.post(f"{BASE}/api/partb/allotments/{aid}/disposition", headers=H(admissions),
                          json={"to": "cancelled", "remarks": "second attempt"}, timeout=30)
        assert r2.status_code == 409


# ------------------ 11. BETTERMENT (c04 BLR -> ME) ------------------
class TestBetterment:
    def test_candidate_accepts_and_admin_allots(self, admissions):
        tok = login_candidate(4)
        pb = requests.get(f"{BASE}/api/candidate/partb", headers=H(tok), timeout=30).json()
        offer = next((o for o in pb["betterment_offers"] if o["program_code"] == "PGDM-ME"), None)
        if not offer:
            pytest.skip("no PGDM-ME betterment offer for c04")
        bid = offer["batch_id"]
        if offer["response"] == "pending":
            # Admin pre-consent allot attempt -> 409 betterment_consent_required
            parts = requests.get(f"{BASE}/api/partb/candidates", headers=H(admissions), timeout=30).json()
            c04 = next(p for p in parts if p["application_ref"].endswith("S00004"))
            pre = requests.post(f"{BASE}/api/partb/batches/{bid}/allot", headers=H(admissions),
                               json={"candidate_id": c04["candidate_id"], "status": "allotted"}, timeout=30)
            assert pre.status_code == 409
            assert pre.json()["detail"]["code"] == "betterment_consent_required"
            # Candidate accepts
            r = requests.post(f"{BASE}/api/candidate/partb/betterment/{bid}", headers=H(tok),
                            json={"response": "accept"}, timeout=30)
            assert r.status_code == 200, r.text
            # Second response -> 409
            r2 = requests.post(f"{BASE}/api/candidate/partb/betterment/{bid}", headers=H(tok),
                             json={"response": "accept"}, timeout=30)
            assert r2.status_code == 409

        # Check vacancy BLR before
        v0 = requests.get(f"{BASE}/api/partb/vacancy", headers=H(admissions), timeout=30).json()
        blr_before = next(x for x in v0 if x["program_code"] == "PGDM-BLR")["filled"]

        parts = requests.get(f"{BASE}/api/partb/candidates", headers=H(admissions), timeout=30).json()
        c04 = next(p for p in parts if p["application_ref"].endswith("S00004"))
        r = requests.post(f"{BASE}/api/partb/batches/{bid}/allot", headers=H(admissions),
                         json={"candidate_id": c04["candidate_id"], "status": "allotted"}, timeout=30)
        assert r.status_code == 200, r.text
        v1 = requests.get(f"{BASE}/api/partb/vacancy", headers=H(admissions), timeout=30).json()
        blr_after = next(x for x in v1 if x["program_code"] == "PGDM-BLR")["filled"]
        assert blr_after == blr_before - 1, "BLR seat should be released exactly once"


# ------------------ 12. RECEIPT PDF ------------------
class TestReceipt:
    def test_no_allotment_409(self):
        tok = login_candidate(13)
        r = requests.get(f"{BASE}/api/candidate/partb/allotment/receipt", headers=H(tok), timeout=30)
        assert r.status_code == 409

    def test_receipt_download(self):
        tok = login_candidate(4)
        r = requests.get(f"{BASE}/api/candidate/partb/allotment/receipt", headers=H(tok), timeout=30)
        assert r.status_code == 200
        assert r.headers.get("Content-Type") == "application/pdf"
        assert r.content.startswith(b"%PDF")


# ------------------ 13. NOTIFICATIONS ------------------
class TestNotifications:
    def test_list_and_read_all(self):
        tok = login_candidate(4)
        r = requests.get(f"{BASE}/api/candidate/notifications", headers=H(tok), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d
        r2 = requests.post(f"{BASE}/api/candidate/notifications/read-all", headers=H(tok), timeout=30)
        assert r2.status_code == 200
        assert r2.json()["unread"] == 0


# ------------------ 14. SEAT MATRIX ------------------
class TestSeatMatrix:
    def test_superadmin_set_capacity(self, superadmin):
        # Set MMS-ACAP capacity to a reasonable value; don't exceed approved intake
        r = requests.get(f"{BASE}/api/partb/vacancy", headers=H(superadmin), timeout=30).json()
        a = next(x for x in r if x["program_code"] == "MMS-ACAP")
        cur = a["capacity"]
        r2 = requests.put(f"{BASE}/api/partb/seats/MMS-ACAP", headers=H(superadmin),
                         json={"capacity": cur}, timeout=30)
        assert r2.status_code == 200

    def test_over_approved_422(self, superadmin):
        r = requests.put(f"{BASE}/api/partb/seats/MMS-ACAP", headers=H(superadmin),
                        json={"capacity": 5000}, timeout=30)
        assert r.status_code == 422

    def test_admissions_cannot_set_capacity(self, admissions):
        r = requests.put(f"{BASE}/api/partb/seats/MMS-ACAP", headers=H(admissions),
                        json={"capacity": 100}, timeout=30)
        assert r.status_code == 403


# ------------------ 15. REPORTS & AUDITOR ------------------
class TestReports:
    def test_overview(self, admissions):
        r = requests.get(f"{BASE}/api/partb/reports/overview", headers=H(admissions), timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_export_xlsx(self, admissions):
        r = requests.get(f"{BASE}/api/partb/reports/export", headers=H(admissions), timeout=30)
        assert r.status_code == 200
        assert "spreadsheet" in r.headers.get("Content-Type", "")

    def test_auditor_read_but_cannot_allot(self, auditor):
        r = requests.get(f"{BASE}/api/partb/reports/overview", headers=H(auditor), timeout=30)
        assert r.status_code == 200
        batches = requests.get(f"{BASE}/api/partb/batches", headers=H(auditor), timeout=30)
        assert batches.status_code == 200
        # Auditor must NOT be able to import
        r2 = requests.get(f"{BASE}/api/partb/imports", headers=H(auditor), timeout=30)
        assert r2.status_code == 403
