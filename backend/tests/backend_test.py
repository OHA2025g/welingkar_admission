"""
Backend tests for WeSchool Admissions Portal Phase 0 POC.
Covers: health, Email OTP (send/verify/cooldown/lock/replay), WhatsApp OTP (expected fail),
Stripe payments (orders idempotency), MOCKED refunds state machine, PDFs, webhook idempotency.
"""
import hashlib
import hmac
import json
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hub-preview-32.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
EMAIL_SINK = "delivered@resend.dev"
SAMPLE_REF = "WS-2027-PGDM-000123"


@pytest.fixture(scope="session")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    # Phase 1: Phase 0 endpoints now require auth. super_admin has payments.read + candidates.read.
    r = s.post(f"{API}/auth/staff/login",
               json={"email": "superadmin@weschool-demo.in", "password": "SuperAdmin@2026"}, timeout=20)
    if r.status_code == 200 and r.json().get("step_up_required"):
        body = r.json()
        r = s.post(f"{API}/auth/staff/login/complete",
                   json={"challenge_id": body["challenge_id"], "code": body["debug_code"]}, timeout=20)
    if r.status_code == 200 and r.json().get("access_token"):
        s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


@pytest.fixture(scope="session")
def http_accounts():
    """Separate session for accounts_operator (has payments.refund)."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/staff/login",
               json={"email": "accounts@weschool-demo.in", "password": "Staff@2026"}, timeout=20)
    if r.status_code == 200 and r.json().get("step_up_required"):
        body = r.json()
        r = s.post(f"{API}/auth/staff/login/complete",
                   json={"challenge_id": body["challenge_id"], "code": body["debug_code"]}, timeout=20)
    if r.status_code == 200 and r.json().get("access_token"):
        s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


# ------------ Health / meta ------------
class TestHealth:
    def test_health(self, http):
        r = http.get(f"{API}/poc/health", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["whatsapp"]["configured"] is True
        assert d["payments"]["refunds_mocked"] is True
        assert d["email"]["configured"] is True

    def test_openapi(self, http):
        r = http.get(f"{API}/openapi.json", timeout=20)
        assert r.status_code == 200
        assert "paths" in r.json()


# ------------ Email OTP ------------
class TestEmailOtp:
    def test_invalid_email_422(self, http):
        r = http.post(f"{API}/otp/send", json={"channel": "email", "destination": "not-an-email"})
        assert r.status_code == 422

    def test_send_verify_wrong_then_correct_then_replay(self, http):
        # Send to sink -> debug_code
        r = http.post(f"{API}/otp/send", json={"channel": "email", "destination": EMAIL_SINK})
        if r.status_code == 429:
            pytest.skip(f"Rate-limited on sink: {r.json()}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "debug_code" in d, "debug_code must be returned for sink"
        assert d["attempts_left"] == 5
        cid, code = d["id"], d["debug_code"]

        # Wrong code -> 400 invalid_code, attempts_left=4
        r = http.post(f"{API}/otp/verify", json={"challenge_id": cid, "code": "000000" if code != "000000" else "111111"})
        assert r.status_code == 400, r.text
        err = r.json()["detail"]
        assert err["code"] == "invalid_code"
        assert err["attempts_left"] == 4

        # Correct -> verified
        r = http.post(f"{API}/otp/verify", json={"challenge_id": cid, "code": code})
        assert r.status_code == 200
        assert r.json()["verified"] is True

        # Replay -> 409 already_used
        r = http.post(f"{API}/otp/verify", json={"challenge_id": cid, "code": code})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "already_used"

    def test_resend_cooldown_429(self, http):
        # Fresh send
        r1 = http.post(f"{API}/otp/send", json={"channel": "email", "destination": EMAIL_SINK})
        if r1.status_code == 429:
            pytest.skip(f"Rate-limited on sink: {r1.json()}")
        assert r1.status_code == 200
        # Immediate resend -> cooldown
        r2 = http.post(f"{API}/otp/send", json={"channel": "email", "destination": EMAIL_SINK})
        assert r2.status_code == 429
        assert r2.json()["detail"]["code"] in ("resend_cooldown", "rate_limited")

    def test_lock_after_5_wrong(self, http):
        # Use a non-sink @resend.dev address so we don't eat sink rate limit
        dest = f"delivered+t1lock-{uuid.uuid4().hex[:6]}@resend.dev"
        r = http.post(f"{API}/otp/send", json={"channel": "email", "destination": dest})
        if r.status_code == 429:
            pytest.skip("Rate limited")
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        last = None
        for _ in range(5):
            last = http.post(f"{API}/otp/verify", json={"challenge_id": cid, "code": "000000"})
        assert last.status_code in (400, 423), last.text
        # One more should definitely be locked
        r2 = http.post(f"{API}/otp/verify", json={"challenge_id": cid, "code": "000000"})
        assert r2.status_code == 423
        assert r2.json()["detail"]["code"] == "locked"


# ------------ WhatsApp OTP (expected to fail delivery) ------------
class TestWhatsAppOtp:
    def test_invalid_phone_422(self, http):
        r = http.post(f"{API}/otp/send", json={"channel": "whatsapp", "destination": "12345"})
        assert r.status_code == 422

    def test_valid_phone_mocked(self, http):
        r = http.post(f"{API}/otp/send", json={"channel": "whatsapp", "destination": "+919921147068"})
        assert r.status_code in (200, 429), r.text
        if r.status_code == 200:
            assert r.json()["mocked"] is True and len(r.json()["debug_code"]) == 6


# ------------ Stripe payment orders ------------
@pytest.fixture(scope="class")
def created_order(http):
    key = f"TEST-{uuid.uuid4().hex}"
    payload = {
        "fee_code": "application_fee",
        "candidate_name": "Test Candidate",
        "candidate_email": "test@example.com",
        "application_ref": SAMPLE_REF,
        "origin_url": BASE_URL,
        "idempotency_key": key,
    }
    r = http.post(f"{API}/payments/orders", json=payload)
    assert r.status_code == 200, r.text
    return {"payload": payload, "order": r.json(), "key": key}


class TestPayments:
    def test_create_order(self, created_order):
        o = created_order["order"]
        assert o["status"] == "pending"
        assert o["amount"] == 1500
        assert o["currency"] == "INR"
        assert o["checkout_url"].startswith("https://")

    def test_idempotent_replay(self, http, created_order):
        r = http.post(f"{API}/payments/orders", json=created_order["payload"])
        assert r.status_code == 200
        d = r.json()
        assert d.get("idempotent_replay") is True
        assert d["id"] == created_order["order"]["id"]

    def test_idempotency_conflict(self, http, created_order):
        bad = dict(created_order["payload"], candidate_name="Someone Else")
        r = http.post(f"{API}/payments/orders", json=bad)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "idempotency_conflict"

    def test_refund_on_unpaid_409(self, http_accounts, created_order):
        oid = created_order["order"]["id"]
        r = http_accounts.post(f"{API}/payments/orders/{oid}/refunds",
                      json={"reason": "test", "idempotency_key": f"TEST-{uuid.uuid4().hex}"})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "not_refundable"


# ------------ PDFs ------------
class TestPDF:
    def test_application_pdf(self, http):
        r = http.get(f"{API}/pdf/application/{SAMPLE_REF}")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"

    def test_application_pdf_not_found(self, http):
        r = http.get(f"{API}/pdf/application/NON-EXISTENT-REF")
        assert r.status_code == 404

    def test_receipt_pdf_unpaid_409(self, http, created_order):
        oid = created_order["order"]["id"]
        r = http.get(f"{API}/pdf/receipt/{oid}")
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "not_paid"


# ------------ Webhook idempotency ------------
class TestWebhook:
    def test_fake_event_processed_then_duplicate(self, http, created_order):
        session_id = created_order["order"].get("provider_session_id")
        if not session_id:
            pytest.skip("No session id")
        event = {
            "id": f"evt_test_{uuid.uuid4().hex}",
            "type": "checkout.session.completed",
            "data": {"object": {"id": session_id}},
        }
        raw = json.dumps(event).encode()
        headers = {"Content-Type": "application/json"}
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET") or ""
        if secret:
            ts = str(int(time.time()))
            sig = hmac.new(secret.encode(), f"{ts}.{raw.decode()}".encode(), hashlib.sha256).hexdigest()
            headers["Stripe-Signature"] = f"t={ts},v1={sig}"
        r1 = http.post(f"{API}/webhook/stripe", data=raw, headers=headers)
        assert r1.status_code == 200
        assert r1.json()["status"] in ("processed", "duplicate")
        r2 = http.post(f"{API}/webhook/stripe", data=raw, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "duplicate"
