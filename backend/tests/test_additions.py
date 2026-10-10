"""Checks for signed staff step-up, paged lists, health, help text, and report drill-down."""
import os

import requests

BASE = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8001/api")


def test_privileged_login_needs_email_code():
    r = requests.post(f"{BASE}/auth/staff/login",
                      json={"email": "superadmin@weschool-demo.in", "password": "SuperAdmin@2026"}, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["step_up_required"] is True
    assert body.get("debug_code")
    done = requests.post(f"{BASE}/auth/staff/login/complete",
                         json={"challenge_id": body["challenge_id"], "code": body["debug_code"]}, timeout=20)
    assert done.status_code == 200, done.text
    assert done.json()["user"]["role"] == "super_admin"
    me = requests.get(f"{BASE}/dashboard", headers={"Authorization": f"Bearer {done.json()['access_token']}"}, timeout=20)
    assert me.status_code == 200
    assert set(me.json()["health"]) == {"mongo", "storage", "email"}


def test_auditor_login_stays_password_only():
    r = requests.post(f"{BASE}/auth/staff/login",
                      json={"email": "auditor@weschool-demo.in", "password": "Staff@2026"}, timeout=20)
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()
    assert "step_up_required" not in r.json()


def test_paged_applications_and_help_and_people():
    login = requests.post(f"{BASE}/auth/staff/login",
                          json={"email": "auditor@weschool-demo.in", "password": "Staff@2026"}, timeout=20)
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    apps = requests.get(f"{BASE}/admin/applications", params={"page": 1, "page_size": 50}, headers=headers, timeout=30)
    assert apps.status_code == 200, apps.text
    body = apps.json()
    assert "rows" in body and "total" in body and body["page_size"] == 50
    assert len(body["rows"]) <= 50
    cancellations = requests.get(f"{BASE}/partb/cancellations", params={"page": 1, "page_size": 50}, headers=headers, timeout=30)
    assert cancellations.status_code == 200, cancellations.text
    assert "rows" in cancellations.json() and "total" in cancellations.json()
    people = requests.get(f"{BASE}/reports/people", params={"slice": "state", "key": "Maharashtra"}, headers=headers, timeout=30)
    assert people.status_code == 200, people.text
    assert people.json()["masked"] is True
    cand = requests.post(f"{BASE}/auth/candidate/login",
                         json={"email": "candidate01@example.com", "password": "Candidate@2026"}, timeout=20)
    assert cand.status_code == 200, cand.text
    cheaders = {"Authorization": f"Bearer {cand.json()['access_token']}"}
    help_fee = requests.get(f"{BASE}/candidate/help", params={"topic": "fee"}, headers=cheaders, timeout=20)
    assert help_fee.status_code == 200, help_fee.text
    assert any("Admission fee" in line or "fee" in line.lower() for line in help_fee.json()["lines"])
    home = requests.get(f"{BASE}/candidate/dashboard", headers=cheaders, timeout=20)
    assert home.status_code == 200
    assert "countdowns" in home.json() and "next_step" in home.json()
    booking = next(item for item in home.json()["countdowns"] if item["key"] == "pi_booking")
    assert booking["label"] == "PI booking closes"
    assert booking["detail"].endswith(" IST")
