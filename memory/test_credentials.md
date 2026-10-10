# Test Credentials (Phase 1)

Staff portal: /staff/login (POST /api/auth/staff/login). Candidate portal: /candidate/login (POST /api/auth/candidate/login).
Candidates cannot sign in on the staff portal, and staff cannot sign in on the candidate portal.

## Staff (one per role)
| Role | Email | Password |
|---|---|---|
| Super Admin | superadmin@weschool-demo.in | SuperAdmin@2026 |
| Admissions Operator | admissions@weschool-demo.in | Staff@2026 |
| Document Verifier | verifier@weschool-demo.in | Staff@2026 |
| GA/PI Panelist | panelist@weschool-demo.in | Staff@2026 |
| Interview Coordinator | coordinator@weschool-demo.in | Staff@2026 |
| Accounts Operator | accounts@weschool-demo.in | Staff@2026 |
| Result Approver | results@weschool-demo.in | Staff@2026 |
| Auditor (read-only) | auditor@weschool-demo.in | Staff@2026 |

## Candidates (seeded)
candidate01@example.com … candidate10@example.com, password `Candidate@2026`
- 01–07 verified; 08–09 partially_verified (email only); 10 registered (none verified)
- example.com cannot receive email, so email-OTP login/recovery for seeded candidates won't arrive. Use a new registration instead.

## Registering new candidates for OTP tests
- Use any `@resend.dev` address (e.g. delivered+anything@resend.dev). The API echoes `debug_code` ONLY for this Resend test domain.
- WhatsApp OTP is MOCKED (no Twilio template ContentSid). The API returns `mocked: true` and `debug_code`.
- Mobile must be unique per candidate (10-digit Indian or E.164).
- OTP rules: 10 min expiry, 60s resend cooldown, 5 attempts, 5 sends/hour per destination.

## Sessions
- Idle timeout: staff 15 min, candidate 30 min. 5 failed logins per IP+email → 15 min lockout.
- Auth uses the httpOnly cookie `ws_session` or `Authorization: Bearer <access_token>` (returned by login).

## Phase 0
- Payments console /poc requires payments.read (Accounts Operator or Super Admin). Refunds require payments.refund (Accounts Operator).
- Stripe test card 4242 4242 4242 4242, any future expiry, any CVC.

## Phase 2 seeded candidate stages (password Candidate@2026)
- candidate01: draft (3/7 sections), fee unpaid → submit must be blocked (fee_unpaid)
- candidate02: fee paid, draft 5/7 sections (exams/preferences/signature pending) → good for completing and submitting
- candidate03, candidate07: paid + submitted (PDF available)
- candidate04: paid + submitted + declaration + data confirmation
- candidate05: paid, no form data yet
- candidate06: verified, nothing started
- candidate08/09 partially verified, candidate10 registered only
- Seeded paid orders use provider "seed" (not Stripe). New candidates pay via Stripe test checkout (card 4242 4242 4242 4242).
- Staff: Admissions Operator / Super Admin → /staff/part-a, /staff/applications (export, correction). Auditor: read-only view, no export/correction.

## Phase 3 (Interviews & Results) seed — password Staff@2026 for staff, Candidate@2026 for candidates
- Extra panelists: panelist2@weschool-demo.in (Dr. Sunita Menon), panelist3@weschool-demo.in (Prof. Rajiv Bhatt)
- Extra verified + submitted candidates: candidate11..candidate14@example.com
- Sessions (dates relative to seed day, IST): past GA Mumbai (-6d, panelist+panelist2), past PI Mumbai Room 101 (-5d, panelist),
  past PI Mumbai Room 102 (-1d, panelist2, candidate12 booked & unscored), future GA/PI sessions (+7..+9d); PI Bengaluru Room B201 (+9d) has capacity 1 (race test).
- candidate03/04/07/11: GA + PI booked, attended, scored (submitted, locked). candidate07 & 11 are TFW-eligible (income 4.5 L).
- candidate12: GA (past, unscored by panelist) + PI past session (panelist2, unscored) → scoring test.
- candidate13: MMS-only → institute selection, no GA/PI. candidate14: submitted + PIQ, no booking → PI book/reschedule test.
- Result versions: v1 published (by results@), v2 generated (unpublished). Only result_approver can approve/publish.
- panelist3 has only future sessions; is NOT assigned to the past GA session (403 expected).

## Phase 4 (Part B) seed — re-created only when partb_import_batches is empty
- Extra verified+submitted candidates: candidate15..candidate18@example.com (MMS-AGCAP only; consented, docs verified, merit #1-4). MMS-AGCAP Part B capacity = 1 → seat race fixture.
- candidate03: consented; counselling docs in DISCREPANCY (2nd checklist item). candidate04: allotted PGDM-BLR (receipt available) + waitlisted PGDM-ME choice 1 → pending betterment offer (Waiting list 1 · PGDM-ME).
- candidate07: ON HOLD in PGDM-EB (docs verified). candidate11: consented, docs registered (awaiting verification). candidate13: eligible MMS-ACAP, consented, no docs. candidate14: rejected only → Part B ineligible.
- Batches: merit round 1 for PGDM-BLR/EB/HC/ME, MMS-ACAP, MMS-AGCAP (open d-3..d+14); waitlist 1 for PGDM-ME, PGDM-MUM (d-1..d+10).
- verifier@weschool-demo.in (Staff@2026) has ONLY documents.verify (worklists). admissions@ manages imports/batches/allotment; superadmin@ also seats.manage.
- Reset Part B: delete partb_* collections, seat_events, notifications, files{kind:partb_doc} then restart backend.

## Phase 5 (Finance, Cancellation & Admin)
- Step-up refund tester (Accounts Operator, real Resend email to the test inbox, API echoes debug_code): delivered+accounts@resend.dev / Staff@2026
- accounts@weschool-demo.in can't receive email, so it can't finish a refund OTP. Use the step-up tester above for refunds.
- Refunds (POST /api/payments/orders/{id}/refunds and POST /api/accounts/cancellations/{id}/refund) require otp_challenge_id + otp_code from POST /api/accounts/step-up/send (purpose step_up_refund, one code per refund).
- Seed (re-created only when no admission_fee orders exist): candidate04 admission fee PAID (PGDM-BLR allotted); candidate11 PROVISIONAL PGDM-ME, admission fee PAID, cancellation REQUESTED; candidate13 PROVISIONAL MMS-ACAP, offline NEFT payment AWAITING VERIFICATION with no proof (proof needed to verify).
- Admission fee = cycle admission_fee_inr (₹1,00,000). Policy admission_rules: on_hold_consumes_seat (true), programme_start_date, offline_modes.
- Reset Part B + finance: PYTHONPATH=/app/backend python /app/backend/tests/reset_phase45.py, then restart backend.
