"""
Phase 1 backend tests: staff/candidate auth, RBAC, cycles/programs/policies CRUD, audit.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hub-preview-32.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

STAFF = {
    "super_admin": ("superadmin@weschool-demo.in", "SuperAdmin@2026"),
    "admissions_operator": ("admissions@weschool-demo.in", "Staff@2026"),
    "document_verifier": ("verifier@weschool-demo.in", "Staff@2026"),
    "panelist": ("panelist@weschool-demo.in", "Staff@2026"),
    "interview_coordinator": ("coordinator@weschool-demo.in", "Staff@2026"),
    "accounts_operator": ("accounts@weschool-demo.in", "Staff@2026"),
    "result_approver": ("results@weschool-demo.in", "Staff@2026"),
    "auditor": ("auditor@weschool-demo.in", "Staff@2026"),
}

CANDIDATE_EMAIL = "candidate01@example.com"
CANDIDATE_PW = "Candidate@2026"


def _login(email, pw, staff=True):
    path = "/auth/staff/login" if staff else "/auth/candidate/login"
    r = requests.post(f"{API}{path}", json={"email": email, "password": pw}, timeout=20)
    if staff and r.status_code == 200 and r.json().get("step_up_required"):
        body = r.json()
        r = requests.post(f"{API}/auth/staff/login/complete",
                          json={"challenge_id": body["challenge_id"], "code": body["debug_code"]}, timeout=20)
    return r


def _tok(email, pw, staff=True):
    r = _login(email, pw, staff)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------------------- Staff login (all 8 roles) ----------------------
class TestStaffLogin:
    @pytest.mark.parametrize("role,creds", list(STAFF.items()))
    def test_each_role_login(self, role, creds):
        email, pw = creds
        r = _login(email, pw, staff=True)
        assert r.status_code == 200, f"{role}: {r.text}"
        d = r.json()
        assert d["user"]["role"] == role
        assert d["user"]["home"] == "/staff/dashboard"
        assert isinstance(d["access_token"], str) and len(d["access_token"]) > 20
        assert "permissions" in d["user"]
        assert "idle_minutes" in d["user"]

    def test_candidate_rejected_on_staff_login(self):
        r = _login(CANDIDATE_EMAIL, CANDIDATE_PW, staff=True)
        assert r.status_code == 401

    def test_staff_rejected_on_candidate_login(self):
        email, pw = STAFF["super_admin"]
        r = _login(email, pw, staff=False)
        assert r.status_code == 401

    def test_me_endpoint(self):
        tok = _tok(*STAFF["super_admin"])
        r = requests.get(f"{API}/auth/me", headers=H(tok))
        assert r.status_code == 200
        assert r.json()["role"] == "super_admin"

    def test_unauth_401(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_brute_force_lockout(self):
        # Use throwaway nonexistent email to not harm real accounts
        email = f"nobody+{uuid.uuid4().hex[:8]}@weschool-demo.in"
        last = None
        for _ in range(5):
            last = requests.post(f"{API}/auth/staff/login", json={"email": email, "password": "wrong"})
            assert last.status_code == 401
        # Next attempt should be locked
        r = requests.post(f"{API}/auth/staff/login", json={"email": email, "password": "wrong"})
        assert r.status_code == 429
        assert r.json()["detail"]["code"] == "locked_out"


# ---------------------- RBAC ----------------------
# role -> list of (method, path, expected_allowed_bool)
RBAC_CASES = [
    # super_admin only
    ("GET", "/admin/users", {"super_admin"}),
    ("GET", "/admin/roles", {"super_admin", "auditor"}),
    ("GET", "/audit", {"super_admin", "auditor"}),
    # modules
    ("GET", "/panel/sessions", {"panelist"}),
    ("GET", "/modules/documents", {"document_verifier"}),
    ("GET", "/interviews/sessions", {"interview_coordinator"}),
    ("GET", "/results/versions", {"result_approver", "admissions_operator", "super_admin", "auditor"}),
    ("GET", "/reports/evaluation", {"super_admin", "admissions_operator", "interview_coordinator", "result_approver", "auditor"}),
    ("GET", "/admin/applications", {"admissions_operator", "super_admin", "auditor"}),
    ("GET", "/modules/reports", {"super_admin", "admissions_operator", "accounts_operator",
                                   "result_approver", "auditor"}),
    # candidates listing (candidates.read)
    ("GET", "/admin/candidates", {"super_admin", "admissions_operator", "auditor"}),
    # cycles / programs read
    ("GET", "/cycles", set(STAFF.keys()) - {"panelist", "document_verifier"}),
    ("GET", "/programs", set(STAFF.keys()) - {"panelist", "document_verifier"}),
    # policies read
    ("GET", "/policies", {"super_admin", "auditor"}),
]


class TestRBAC:
    @pytest.fixture(scope="class")
    def tokens(self):
        return {role: _tok(email, pw) for role, (email, pw) in STAFF.items()}

    @pytest.mark.parametrize("method,path,allowed", RBAC_CASES)
    def test_endpoint_access(self, tokens, method, path, allowed):
        for role, tok in tokens.items():
            r = requests.request(method, f"{API}{path}", headers=H(tok))
            if role in allowed:
                assert r.status_code == 200, f"{role} should access {path}: {r.status_code} {r.text[:200]}"
            else:
                assert r.status_code == 403, f"{role} should be forbidden on {path}: {r.status_code}"
                assert r.json()["detail"]["code"] == "forbidden"

    def test_candidate_token_denied_on_staff_endpoints(self):
        tok = _tok(CANDIDATE_EMAIL, CANDIDATE_PW, staff=False)
        for path in ["/admin/users", "/dashboard", "/cycles", "/admin/candidates", "/audit", "/policies"]:
            r = requests.get(f"{API}{path}", headers=H(tok))
            assert r.status_code == 403, f"candidate should be denied on {path}: {r.status_code}"

    def test_unauth_401_on_protected(self):
        for path in ["/admin/users", "/dashboard", "/cycles", "/audit"]:
            r = requests.get(f"{API}{path}")
            assert r.status_code == 401

    def test_cycles_write_forbidden_for_auditor(self):
        tok = _tok(*STAFF["auditor"])
        r = requests.post(f"{API}/cycles", headers=H(tok), json={
            "code": "TEST-X", "name": "x", "application_open": "2026-01-01",
            "application_close": "2026-02-01", "application_fee_inr": 1500})
        assert r.status_code == 403

    def test_payments_refund_only_accounts(self):
        # Super admin has payments.read but NOT payments.refund
        tok_sa = _tok(*STAFF["super_admin"])
        r = requests.post(f"{API}/payments/orders/000000000000000000000000/refunds",
                          headers=H(tok_sa), json={"reason": "x", "idempotency_key": uuid.uuid4().hex})
        assert r.status_code == 403, r.text
        tok_acc = _tok(*STAFF["accounts_operator"])
        r = requests.post(f"{API}/payments/orders/000000000000000000000000/refunds",
                          headers=H(tok_acc), json={"reason": "x", "idempotency_key": uuid.uuid4().hex})
        # Allowed by RBAC => reaches handler which 404s on fake id
        assert r.status_code in (404, 409, 422), r.text

    def test_denied_requests_create_audit(self):
        # trigger a denied call via panelist to /admin/users
        tok = _tok(*STAFF["panelist"])
        r = requests.get(f"{API}/admin/users", headers=H(tok))
        assert r.status_code == 403
        # auditor can see audit
        atok = _tok(*STAFF["auditor"])
        r2 = requests.get(f"{API}/audit?outcome=denied&page_size=10", headers=H(atok))
        assert r2.status_code == 200
        items = r2.json()["items"]
        assert any(i["action"] == "access.denied" for i in items)


# ---------------------- Cycles CRUD ----------------------
class TestCyclesCRUD:
    @pytest.fixture(scope="class")
    def sa_tok(self):
        return _tok(*STAFF["super_admin"])

    def test_list_cycles_has_seed(self, sa_tok):
        r = requests.get(f"{API}/cycles", headers=H(sa_tok))
        assert r.status_code == 200
        cycles = r.json()
        assert any(c["status"] == "active" for c in cycles)

    def test_create_draft_then_update(self, sa_tok):
        code = f"TEST-{uuid.uuid4().hex[:6].upper()}"
        body = {"code": code, "name": "TEST Cycle", "status": "draft",
                "application_open": "2027-01-01", "application_close": "2027-03-01",
                "application_fee_inr": 1500}
        r = requests.post(f"{API}/cycles", headers=H(sa_tok), json=body)
        assert r.status_code == 200, r.text
        c = r.json()
        cid = c["id"]
        assert c["status"] == "draft"
        assert c["version"] == 1

        # GET verifies persistence
        r = requests.get(f"{API}/cycles", headers=H(sa_tok))
        assert any(x["id"] == cid for x in r.json())

        # Try activating -> should 409 another_active
        r = requests.patch(f"{API}/cycles/{cid}", headers=H(sa_tok),
                           json={**body, "status": "active", "version": 1})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "another_active"

        # Update name
        r = requests.patch(f"{API}/cycles/{cid}", headers=H(sa_tok),
                           json={**body, "name": "TEST Cycle Updated", "version": 1})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "TEST Cycle Updated"
        assert r.json()["version"] == 2

        # Stale version
        r = requests.patch(f"{API}/cycles/{cid}", headers=H(sa_tok),
                           json={**body, "name": "TEST Cycle Stale", "version": 1})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "stale_version"

    def test_close_before_open_422(self, sa_tok):
        r = requests.post(f"{API}/cycles", headers=H(sa_tok), json={
            "code": f"TEST-{uuid.uuid4().hex[:6].upper()}", "name": "Bad Dates",
            "application_open": "2027-03-01", "application_close": "2027-01-01",
            "application_fee_inr": 1500})
        assert r.status_code == 422

    def test_duplicate_code(self, sa_tok):
        # cycle 2026-28 seeded with code "2026-28"
        r = requests.post(f"{API}/cycles", headers=H(sa_tok), json={
            "code": "2026-28", "name": "Dup", "application_open": "2027-01-01",
            "application_close": "2027-02-01", "application_fee_inr": 1500})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "duplicate_code"


# ---------------------- Programs CRUD ----------------------
class TestProgramsCRUD:
    @pytest.fixture(scope="class")
    def sa_tok(self):
        return _tok(*STAFF["super_admin"])

    @pytest.fixture(scope="class")
    def active_cycle_id(self, sa_tok):
        r = requests.get(f"{API}/cycles", headers=H(sa_tok))
        return next(c["id"] for c in r.json() if c["status"] == "active")

    def test_list_11_programs(self, sa_tok, active_cycle_id):
        r = requests.get(f"{API}/programs?cycle_id={active_cycle_id}", headers=H(sa_tok))
        assert r.status_code == 200
        progs = r.json()
        assert len(progs) >= 11, f"expected 11 seeded programs, got {len(progs)}"

    def test_create_and_tfw_validation(self, sa_tok, active_cycle_id):
        code = f"T{uuid.uuid4().hex[:5].upper()}"
        body = {"cycle_id": active_cycle_id, "code": code, "name": "TEST Program",
                "route": "Route-A", "campus": "Mumbai", "duration_months": 24,
                "seat_capacity": 60, "tfw_seats": 5}
        r = requests.post(f"{API}/programs", headers=H(sa_tok), json=body)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]

        # TFW > capacity -> 422
        bad = {**body, "code": f"T{uuid.uuid4().hex[:5].upper()}", "tfw_seats": 100}
        r = requests.post(f"{API}/programs", headers=H(sa_tok), json=bad)
        assert r.status_code == 422

        # duplicate code -> 409
        r = requests.post(f"{API}/programs", headers=H(sa_tok), json=body)
        assert r.status_code == 409

        # update seats
        r = requests.patch(f"{API}/programs/{pid}", headers=H(sa_tok),
                           json={**body, "seat_capacity": 80, "version": 1})
        assert r.status_code == 200
        assert r.json()["seat_capacity"] == 80


# ---------------------- Policies ----------------------
class TestPolicies:
    @pytest.fixture(scope="class")
    def sa_tok(self):
        return _tok(*STAFF["super_admin"])

    def test_list_policies(self, sa_tok):
        r = requests.get(f"{API}/policies", headers=H(sa_tok))
        assert r.status_code == 200
        keys = {p["key"] for p in r.json()}
        assert {"tfw_rules", "refund_policy"} <= keys

    def test_refund_draft_and_activate(self, sa_tok):
        content = {"application_fee_refundable": False, "processing_fee_inr": 500,
                   "tiers": [{"label": "Before start", "days_before_start_min": 30, "refund_percent": 80},
                             {"label": "Just before", "days_before_start_min": 7, "refund_percent": 30}],
                   "notes": "test"}
        r = requests.post(f"{API}/policies/refund_policy/versions", headers=H(sa_tok),
                          json={"content": content, "change_note": "TEST draft"})
        assert r.status_code == 200, r.text
        v = r.json()["version"]
        assert r.json()["status"] == "draft"

        r = requests.post(f"{API}/policies/refund_policy/versions/{v}/activate", headers=H(sa_tok))
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "active"

        # Auditor cannot create a draft
        atok = _tok(*STAFF["auditor"])
        r = requests.post(f"{API}/policies/refund_policy/versions", headers=H(atok),
                          json={"content": content, "change_note": "nope"})
        assert r.status_code == 403


# ---------------------- Audit log ----------------------
class TestAudit:
    def test_super_admin_can_view(self):
        tok = _tok(*STAFF["super_admin"])
        r = requests.get(f"{API}/audit?page_size=10", headers=H(tok))
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)
        assert "total" in d

    def test_auditor_cannot_mutate(self):
        tok = _tok(*STAFF["auditor"])
        r = requests.post(f"{API}/cycles", headers=H(tok), json={
            "code": "AUD-X", "name": "x", "application_open": "2027-01-01",
            "application_close": "2027-02-01", "application_fee_inr": 1500})
        assert r.status_code == 403

    def test_filters(self):
        tok = _tok(*STAFF["super_admin"])
        r = requests.get(f"{API}/audit?action=auth.login&page_size=5", headers=H(tok))
        assert r.status_code == 200
        for i in r.json()["items"]:
            assert i["action"].startswith("auth.login")


# ---------------------- Public portal ----------------------
class TestPublicPortal:
    def test_portal_shows_active_cycle_and_programs(self):
        r = requests.get(f"{API}/public/portal")
        assert r.status_code == 200
        d = r.json()
        assert d["cycle"] is not None
        assert d["cycle"]["code"] == "2026-28"
        assert float(d["cycle"]["application_fee_inr"]) == 1500
        assert len(d["programs"]) >= 11


# ---------------------- Candidate registration + verification ----------------------
class TestCandidateRegistration:
    def test_register_and_verify_both_channels(self):
        email = f"delivered+{uuid.uuid4().hex[:8]}@resend.dev"
        mobile = "9" + "".join([str((int(uuid.uuid4().hex[i], 16) % 10)) for i in range(9)])
        body = {"name": "Test User", "email": email, "mobile": mobile,
                "state": "Maharashtra", "city": "Mumbai", "password": "Testpass@2026"}
        r = requests.post(f"{API}/auth/candidate/register", json=body)
        if r.status_code == 429:
            pytest.skip(f"Rate limited: {r.text}")
        assert r.status_code == 200, r.text
        data = r.json()
        tok = data["access_token"]
        assert data["user"]["identity_status"] == "registered"
        em_ch = data["challenges"]["email"]
        wa_ch = data["challenges"]["whatsapp"]
        assert "debug_code" in em_ch, f"email debug_code missing: {em_ch}"
        # WhatsApp mocked
        assert wa_ch.get("mocked") is True or "debug_code" in wa_ch, f"whatsapp: {wa_ch}"
        assert "debug_code" in wa_ch

        # Blocked application before verify
        r = requests.get(f"{API}/candidate/application", headers=H(tok))
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "identity_unverified"

        # Verify email
        r = requests.post(f"{API}/auth/candidate/verification/verify", headers=H(tok),
                          json={"channel": "email", "challenge_id": em_ch["id"], "code": em_ch["debug_code"]})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["identity_status"] == "partially_verified"

        # Still blocked
        r = requests.get(f"{API}/candidate/application", headers=H(tok))
        assert r.status_code == 403

        # Verify whatsapp
        r = requests.post(f"{API}/auth/candidate/verification/verify", headers=H(tok),
                          json={"channel": "whatsapp", "challenge_id": wa_ch["id"], "code": wa_ch["debug_code"]})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["identity_status"] == "verified"

        # Now application accessible
        r = requests.get(f"{API}/candidate/application", headers=H(tok))
        assert r.status_code == 200

    def test_duplicate_email_409(self):
        body = {"name": "Dup", "email": CANDIDATE_EMAIL, "mobile": "9999999991",
                "state": "MH", "city": "Mumbai", "password": "Testpass@2026"}
        r = requests.post(f"{API}/auth/candidate/register", json=body)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "email_exists"


# ---------------------- Admin: create user + temp password ----------------------
class TestAdminUsers:
    def test_create_staff_user_and_login(self):
        sa = _tok(*STAFF["super_admin"])
        email = f"test+{uuid.uuid4().hex[:8]}@weschool-demo.in"
        r = requests.post(f"{API}/admin/users", headers=H(sa),
                          json={"name": "TEST Staff", "email": email, "role": "admissions_operator"})
        assert r.status_code == 200, r.text
        d = r.json()
        temp = d["temporary_password"]
        uid = d["user"]["id"]
        assert d["user"]["must_change_password"] is True

        # Login with temp password
        r = _login(email, temp, staff=True)
        assert r.status_code == 200
        tok = r.json()["access_token"]
        assert r.json()["user"]["must_change_password"] is True

        # Change password
        r = requests.post(f"{API}/auth/change-password", headers=H(tok),
                          json={"current_password": temp, "new_password": "NewPass@2026"})
        assert r.status_code == 200

        # Disable user -> session revoked
        r = requests.patch(f"{API}/admin/users/{uid}", headers=H(sa),
                           json={"status": "disabled"})
        assert r.status_code == 200
        r = requests.get(f"{API}/auth/me", headers=H(tok))
        assert r.status_code == 401

        # Login with disabled -> 403
        r = _login(email, "NewPass@2026", staff=True)
        assert r.status_code == 403

    def test_cannot_change_own_role(self):
        sa = _tok(*STAFF["super_admin"])
        me = requests.get(f"{API}/auth/me", headers=H(sa)).json()
        r = requests.patch(f"{API}/admin/users/{me['id']}", headers=H(sa),
                           json={"role": "auditor"})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "self_change"
