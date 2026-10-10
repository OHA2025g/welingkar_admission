import concurrent.futures as cf
import requests

B = "http://localhost:8001/api"


def login(email, pw, staff=True):
    r = requests.post(f"{B}/auth/{'staff' if staff else 'candidate'}/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    body = r.json()
    if body.get("step_up_required"):
        r = requests.post(f"{B}/auth/staff/login/complete", json={"challenge_id": body["challenge_id"], "code": body["debug_code"]})
        assert r.status_code == 200, r.text
        body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}


acc = login("delivered+accounts@resend.dev", "Staff@2026")
adm = login("admissions@weschool-demo.in", "Staff@2026")
aud = login("auditor@weschool-demo.in", "Staff@2026")
c4 = login("candidate04@example.com", "Candidate@2026", False)
c11 = login("candidate11@example.com", "Candidate@2026", False)
c13 = login("candidate13@example.com", "Candidate@2026", False)

print("c4 fee", requests.get(f"{B}/candidate/admission-fee", headers=c4).json()["paid"])
print("c4 checkout again (expect 409)", requests.post(f"{B}/candidate/admission-fee/checkout", json={"origin_url": "http://x"}, headers=c4).status_code)
print("c4 receipt", requests.get(f"{B}/candidate/admission-fee/receipt", headers=c4).headers.get("content-type"))
print("c13 offline again (expect 409)", requests.post(f"{B}/candidate/admission-fee/offline", data={"mode": "neft", "txn_ref": "ABC12345", "txn_date": "2026-10-01"}, headers=c13).status_code)

rep = requests.get(f"{B}/accounts/payments?fee_code=admission_fee", headers=acc).json()
print("summary", rep["summary"])
off = next(r for r in rep["rows"] if r["status"] == "awaiting_verification")
print("verify w/o proof (expect 422)", requests.post(f"{B}/accounts/payments/{off['id']}/verify", headers=acc).status_code)
print("auditor masked", requests.get(f"{B}/accounts/payments", headers=aud).json()["rows"][0]["candidate_email"])
print("auditor verify (expect 403)", requests.post(f"{B}/accounts/payments/{off['id']}/verify", headers=aud).status_code)
print("auditor export", requests.get(f"{B}/accounts/payments/export", headers=aud).status_code)

paid = next(r for r in rep["rows"] if r["status"] == "paid")
print("refund no otp (expect 422)", requests.post(f"{B}/payments/orders/{paid['id']}/refunds", json={"amount": 1, "reason": "test refund", "idempotency_key": "smoke-noop-1"}, headers=acc).status_code)
print("refund bad otp", requests.post(f"{B}/payments/orders/{paid['id']}/refunds", json={"amount": 1, "reason": "test refund", "idempotency_key": "smoke-noop-2", "otp_challenge_id": "0" * 24, "otp_code": "000000"}, headers=acc).status_code)

v0 = {v["program_code"]: v for v in requests.get(f"{B}/partb/vacancy", headers=adm).json()}
cx = requests.get(f"{B}/partb/cancellations?status=requested", headers=adm).json()
print("pending cancellations", len(cx))
cid = cx[0]["id"]
code = cx[0]["program_code"]
with cf.ThreadPoolExecutor(4) as ex:
    codes = list(ex.map(lambda _: requests.post(f"{B}/partb/cancellations/{cid}/approve", json={"remarks": "approved in smoke"}, headers=adm).status_code, range(4)))
print("parallel approve", sorted(codes))
v1 = {v["program_code"]: v for v in requests.get(f"{B}/partb/vacancy", headers=adm).json()}
print("filled", code, v0[code]["filled"], "->", v1[code]["filled"], "reconciled", v1[code]["reconciled"])
print("c11 cxl receipt", requests.get(f"{B}/candidate/cancellation/receipt", headers=c11).headers.get("content-type"))

su = requests.post(f"{B}/accounts/step-up/send", headers=acc).json()
print("step-up", {k: su.get(k) for k in ("mocked", "delivery_status")}, "debug" in str(su))
chid = su.get("id") or su.get("challenge_id")
body = {"otp_challenge_id": chid, "otp_code": su["debug_code"]}
with cf.ThreadPoolExecutor(3) as ex:
    rs = list(ex.map(lambda _: requests.post(f"{B}/accounts/cancellations/{cid}/refund", json=body, headers=acc), range(3)))
print("parallel refund", [r.status_code for r in rs], [r.json().get("status") for r in rs])
o = requests.get(f"{B}/accounts/payments?fee_code=admission_fee&status=paid", headers=acc).json()["rows"]
print("refunded totals", [(r["candidate_name"], r["amount"], r["refunded_amount"]) for r in o])
print("reuse OTP for another refund (expect 4xx)", requests.post(f"{B}/payments/orders/{paid['id']}/refunds", json={"amount": 1, "reason": "test refund", "idempotency_key": "smoke-reuse", **body}, headers=acc).status_code)
print("overview", requests.get(f"{B}/admin/overview", headers=adm).json()["finance"])
recon = requests.post(f"{B}/accounts/reconciliation/run", headers=acc).json()
print("recon", recon["checked"], [f["issue"] for f in recon["flags"]][:5])
u11 = requests.get(f"{B}/admin/candidates/search?q=candidate11@example.com", headers=adm).json()[0]["id"]
print("360", list(requests.get(f"{B}/admin/candidates/{u11}/360", headers=adm).json().keys()))
print("360 auditor email", requests.get(f"{B}/admin/candidates/{u11}/360", headers=aud).json()["profile"]["email"])
for k in ("application", "allotment", "payment", "cancellation"):
    r = requests.get(f"{B}/admin/print/{k}/{u11}", headers=adm)
    print("print", k, r.status_code, r.headers.get("content-type"))
print("print payment by accounts", requests.get(f"{B}/admin/print/payment/{u11}", headers=acc).status_code)
