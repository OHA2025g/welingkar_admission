# WeSchool (Welingkar) Admissions Portal — PRD

## Original problem statement
Admissions portal (FastAPI + React + MongoDB). The spec is in the SRS, BRD and Implementation Baseline (customer-assets docx). Phases: 0 POC integrations; 1 Foundation (auth, RBAC for 9 roles, cycles/programs, audit log, seed); 2 Candidate Part A; 3 Interviews & results; 4 Part B counselling/allotment; 5 Finance, refunds, cancellations, reports.
Phase 0: Email OTP (Resend, Emergent-managed), WhatsApp OTP (Twilio), Stripe INR checkout + webhook/status verification + idempotent records + full/partial refund, server PDF (application summary/receipt). Asia/Kolkata, INR, /api/openapi.json.

## User decisions
- Stripe on the Emergent shared test key (the claimable sandbox is not available for India). Refunds are MOCKED behind the adapter.
- WhatsApp: optional TWILIO_WHATSAPP_CONTENT_SID. Without it, delivery is MOCKED (code returned in the response). Trial sender: whatsapp:+17372508034.
- Application fee ₹1,500 (env APPLICATION_FEE_INR).

## Architecture
- backend: core.py (db, BaseDocument/PyObjectId, IST, rate limits, event log, indexes); services/{email_service, whatsapp_service, stripe_gateway, pdf_service}; routes/{otp, payments, poc}
- frontend: pages/Console (integration console), pages/PaymentReturn; components/console/*

## Implemented (2026-10-06) — Phase 0
- Email OTP: real delivery via Resend. 6 digits, HMAC-hashed, 10 min TTL, 60s resend cooldown, 5 attempts then locked, single use, 5 sends/hr per destination and 30/hr per IP. debug_code is returned only for delivered@resend.dev.
- WhatsApp OTP: Twilio template path (ContentSid). MOCKED fallback when no SID is set.
- Stripe: INR checkout and an idempotency-key order API (same key with a different payload → 409). Paid status is verified server-side (webhook re-verifies with Stripe, or status poll). Unique provider_event_id dedupe, plus a replay-callback POC endpoint.
- Refunds (MOCKED provider): atomic reservation, cumulative total capped at the paid amount, idempotency key, retry, full and partial.
- PDFs (ReportLab): application summary from the seeded submitted application; receipt only for paid orders.
- Event log and health endpoints; /api/openapi.json and /api/docs.

## Implemented (2026-10-06) — Phase 1 Foundation
- Auth: staff and candidate portals kept separate. bcrypt passwords and a JWT in an httpOnly cookie (or Bearer header). Server-side sessions with idle timeout (staff 15 min, candidate 30 min) plus a client heartbeat and countdown. Lockout after 5 failures per IP+email (15 min). Change password; admin-issued temporary passwords.
- Candidate: registration (name, mobile, email, state, city, password) with dual-channel OTP (email real; WhatsApp MOCKED). Identity states registered → partially_verified → verified, and application access is gated on verified. Login by password or email OTP; recovery via email OTP, which revokes existing sessions.
- RBAC: 9 roles with a permission map (rbac.py), enforced by `require()` on every endpoint. Denied requests are audited. Menus are permission-driven, with a landing dashboard per role and placeholder module endpoints.
- Super Admin: staff users (create, edit, disable, reset; role changes revoke sessions); role/permission matrix; cycles CRUD (one active cycle, version checks); programs CRUD (seats, TFW seats, stages); versioned TFW and refund policies (draft → activate → superseded).
- Audit log: append-only, with actor, action, entity, before/after, field diff, reason, correlation ID and IP. Viewer with filters, pagination and a detail drawer (Super Admin, Auditor).
- Institutional light UI: landing page, auth pages, staff shell, candidate dashboard. The /poc console is now behind the payments.read permission.
- Seed: cycle 2026-28, 11 programmes (1,170 seats), one staff login per role, 10 candidates, policies v1.
- Tests: backend/tests/test_phase1.py (47) and backend_test.py (Phase 0) all pass.

## Implemented (2026-10-06) — Phase 2 Candidate Part A
- Admission info page (dates, fees, scholarships, TFW policy, programmes, news and resources) built from cycle config.
- Application fee: only verified candidates can pay; amount comes from the cycle (₹1,500) via Stripe test checkout. Status is verified server-side; invoice PDF.
- 7 form sections (personal, family, contact, education, work, exams, ranked preferences), defined as Pydantic models in app_schema.py. Drafts autosave and errors come back per field in plain language; progress indicator.
- Photo and signature upload: type, size, magic-byte, dimension and aspect checks; images re-encoded to JPEG and stored in Emergent Object Storage, served via /api/files/{id} with owner/staff checks.
- Submission requires a paid fee, all sections complete and both uploads, and must fall inside the application window. The status change is atomic (duplicates get 409), each version is an immutable snapshot in application_versions, and the PDF includes the photo and signature.
- After submission: PGDM declaration (versioned), preference reset with history (until Part B opens), essays (word limits), PIQ, graduation eligibility declaration, data confirmation (reset when staff make a correction).
- Staff: Part A dashboard (counts, state-wise, first preferences), applications list with filters, read-only detail, audited and versioned corrections, Excel export (Candidates + State-wise sheets). New permissions applications.read/correct/export; Auditor has read-only access with masked contacts.
- Seed: candidates 01 draft, 02 paid draft, 03/07 submitted, 04 submitted + post steps, 05 paid only, 06 verified only. Cycle dates moved to 2026-08-01 → 2027-01-31.
- Tests: tests/test_phase2.py (39) plus the Phase 0/1 suites. Resend's upstream rate limit (429) can cause flaky failures in OTP tests when many run in parallel.

## Backlog
- P1: real gateway decision (D-08: Razorpay / own Stripe key) to un-mock refunds; signed webhooks (STRIPE_WEBHOOK_SECRET); OTP step-up for refunds (FR-060).
- P1: Twilio approved Authentication template or account upgrade to un-mock WhatsApp.
- P2: Phases 2–5 as per plan.

## Implemented (2026-10-06) — Phase 2 fixes + Phase 3 Interviews & Results
- Fixes: shared downloadFile() helper (anchor attached to DOM, filename from Content-Disposition, readable error toasts) for the application PDF, invoice, receipt and Excel exports. Storage retries 429/5xx/network errors with backoff, up to 5 attempts. candidate02 re-seeded via reset_candidate(2).
- New versioned policy 'selection_rules': exam/GA/PI weights summing to 100, selected/waitlist cut-offs, GA rubric, PI question rubric, PI booking cut-off (24h), reschedule limit (2).
- Coordinator (/staff/interviews): locations, rooms, GA/PI sessions with room-capacity, room-clash and panelist-overlap checks; panelist assignment; auto-allocation (atomic reserve, prefers the candidate's home city); candidate and panelist attendance; slot report with Excel export (3 sheets).
- Candidate (/candidate/interviews): PI booking needs a submitted application + PIQ + a programme with PI. Capacity is enforced atomically and booking closes at the cut-off. Reschedule reserves the new slot before releasing the old one (version check). Hall ticket PDF carries the booking version. /candidate/results shows the published version only, with PDF and print.
- Panelist (/staff/scoring): only assigned sessions (403 otherwise); can see photos of assigned candidates only. GA scored as a batch, PI per question; draft saves; submit locks scores (409 on edit). Super Admin can make audited, versioned corrections.
- Evaluation reports (/staff/evaluations): GA/PI scores, per-panelist Excel files, printable GA batch PDF, slot report.
- Results (/staff/results): Admissions Operator / Super Admin generate versions as often as needed (ruleset snapshot, inputs checksum, per-programme ranks; MMS → institute selection; missing scores → incomplete; separate TFW merit list). Only the Result Approver approves and then publishes; the previous published version becomes superseded.
- Seed: 2 locations, 5 rooms, 8 sessions, 3 panelists, candidates 11-14, bookings and scores for 03/04/07/11, v1 published, v2 generated.
- Tests: tests/test_phase3.py (36 tests). The Phase 1 RBAC matrix was updated to the new endpoints.

## Next
- Phase 4: Part B (counselling, consent, document verification, merit/waitlist allotment)

## Implemented (2026-10-06) — Phase 4 Part B (Counselling, Consent, Documents, Allotment)
- Imports (/staff/partb-imports): CSV/XLSX upload in validate (two-step) or insert mode, or built from the published result version. Row-level validation; error report xlsx; checksum blocks re-importing the same file; batch history; rollback (blocked if any candidate in the batch has an allotment).
- Candidate /candidate/part-b: only selected/waitlisted candidates get in. Shows merit/waitlist numbers per course; course + overall consent (versioned; admin correction audited; declining a course where a seat is held is blocked); notifications.
- Documents: checklist depends on candidate status (selected vs waitlisted, category, work, TFW). Uploads are PDF/JPG/PNG ≤2MB in object storage. Re-upload only for docs not yet verified; older versions kept. Separate admission stage unlocks after allotted/provisional.
- Verifier (/staff/verification): only the documents.verify permission. Registered/discrepancy/verified worklists per stage; version-guarded review; a discrepancy needs remarks → notification + email.
- Seats (/staff/allotment): merit/waitlist batches with CRUD (delete blocked once allotted); dashboard with status counts; allot/provisional/hold/reject; on-hold → allotted/provisional/cancelled; cancel by application reference; live colour-coded vacancy; Super Admin seat matrix; reports + 5-sheet Excel export.
- Atomicity (MongoDB is standalone, so no multi-document transactions): atomic $expr seat counter, unique partial index for one seat per candidate, version-guarded supersede/cancel so a seat is released once, compensating rollback on failure, seat_events ledger, and a vacancy check that compares the counter with seat-holding allotments.
- Betterment: fresh consent per waitlist round (pending/accept/decline/expired). New seat reserved → old allotment superseded → old seat released exactly once. Allotment receipt PDF carries a receipt version.
- Emails for allotment, cancellation and discrepancy go through Resend in the background (email_status recorded).
- Seed: candidates 15-18 for the MMS-AGCAP cap-1 race, plus fixtures for each stage. Tests: tests/test_phase4.py (37).

## Implemented (2026-10-06) — Phase 5 Finance, Cancellation & Admin
- Admission fee (/candidate/admission-fee): Stripe test checkout, checked with the gateway on the server, idempotent. A unique partial index allows only one paid admission fee per candidate; a late gateway payment after an offline one becomes `duplicate_payment` (shown as an exception, refundable). Offline path: transaction reference with optional proof → awaiting_verification.
- Accounts (/staff/accounts): payment report + summary, audited xlsx export (masked for Auditor), verify (proof mandatory) / reject (reason) offline payments, record offline payment (amount must equal the fee, proof required, duplicate txn ref blocked), exceptions, reconciliation runs (gateway vs record, refund totals, multiple payments).
- Refunds need a step-up OTP: a real Resend email to the Accounts Operator (purpose step_up_refund, one code per refund). Gateway refund is MOCKED. Reserved-amount guard means total refunds never exceed the paid amount.
- Cancellation: candidate request with reason + bank details (stored separately, shown masked) → approve/reject (cancellations.review) → version-guarded seat release exactly once + vacancy update → refund quote from the refund policy tier and days before programme start (admission_rules.programme_start_date) → Accounts refund with step-up → cancellation receipt PDF; cancellation report xlsx.
- Print centre (/staff/print): application, allotment, payment (admission/application fee) and cancellation PDFs, checked per role and audited. Candidate 360 (/staff/candidates/:id): read-only, Auditor masked, audited correction of name/city/state with a reason. Consolidated dashboard overview (Part A, interviews/results, Part B, finance).
- Policy admission_rules: on_hold_consumes_seat (default true, per decision), offline_modes, verification SLA.
- Seed: c04 paid, c11 provisional + paid + cancellation requested, c13 offline pending. Tests: tests/test_phase5.py (40, all pass), tests/smoke_phase5.py; reset with tests/reset_phase45.py.

## Implemented (2026-10-06) — Local download bundle
- README_LOCAL.md (prerequisites, setup, env tables, seed/restore, default logins, Emergent-dependency matrix); backend/.env.example + frontend/.env.example with placeholders only.
- Local fallbacks: storage writes to LOCAL_STORAGE_DIR when EMERGENT_LLM_KEY is empty or STORAGE_MODE=local; email runs in console mode (logs the email and returns debug_code) when EMERGENT_EMAIL_KEY is empty; COOKIE_SECURE=false for plain http.
- scripts/build_local_zip.sh → frontend/public/downloads/weschool-portal.zip (+ .json size manifest): source without node_modules/build/__pycache__/.git/.env, memory docs, mongodump archive (seed/). Aborts if any real secret value from backend/.env is found in the files or the dump.
- /staff/download (Super Admin, users.manage) with size label, download button and run steps; link in the staff login footer.

## Next (per SRS): remaining reports and hardening, as the root directs
