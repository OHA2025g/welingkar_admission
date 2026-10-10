# WeSchool Admissions Portal: running it on your own machine

React (CRA + craco) frontend · FastAPI backend · MongoDB. All business time is Asia/Kolkata and all money is INR.

## 1. Prerequisites
- Python 3.11
- Node 18 or newer, plus Yarn 1.x (`npm i -g yarn`; use yarn for the project itself, not npm)
- MongoDB 6 or 7 running locally (`mongodb://localhost:27017`), plus MongoDB Database Tools (`mongorestore`) if you want the bundled data snapshot

## 2. Backend
```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
cp .env.example .env        # then edit the values (see section 4)
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```
The `--extra-index-url` is only needed for the `emergentintegrations` package listed in requirements. The portal code does not import it, so you can also delete that line from requirements.txt.

API docs: http://localhost:8001/api/docs

## 3. Frontend
```bash
cd frontend
cp .env.example .env        # REACT_APP_BACKEND_URL=http://localhost:8001
yarn install
yarn start                  # http://localhost:3000
```

## 4. Environment variables
### backend/.env (copy from backend/.env.example)
| Variable | Purpose | Local value |
|---|---|---|
| MONGO_URL | MongoDB connection | `mongodb://localhost:27017` |
| DB_NAME | Database name | `weschool_admissions` |
| CORS_ORIGINS | Allowed frontend origins (comma-separated) | `http://localhost:3000` |
| APP_TIMEZONE | Business timezone | `Asia/Kolkata` |
| COOKIE_SECURE | Set `false` when serving over plain http | `false` |
| JWT_SECRET | Signs session tokens | any long random string |
| OTP_PEPPER | Hashes OTP codes | any long random string |
| APPLICATION_FEE_INR | Default application fee | `1500` |
| ADMIN_EMAIL / ADMIN_PASSWORD | Seeded Super Admin | see section 6 |
| SEED_STAFF_PASSWORD / SEED_CANDIDATE_PASSWORD | Passwords for seeded staff and candidates | `Staff@2026` / `Candidate@2026` |
| EMERGENT_EMAIL_KEY | Email (Resend) via the Emergent email gateway | leave empty → **console email mode** |
| EMAIL_FROM_NAME / EMAIL_REPLY_TO | Sender display name / reply-to address | any |
| TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_FROM | WhatsApp OTP | placeholders are fine |
| TWILIO_WHATSAPP_CONTENT_SID | Approved WhatsApp template | empty → WhatsApp OTP is MOCKED |
| STRIPE_API_KEY | Stripe test key | your own `sk_test_...` |
| STRIPE_WEBHOOK_SECRET | Optional webhook signature check | empty |
| EMERGENT_LLM_KEY | Emergent universal key (used only for object storage) | empty → local disk storage |
| STORAGE_MODE / LOCAL_STORAGE_DIR | `local` forces disk storage at this folder | `local` / `./local_storage` |
| TIGRIS_* | Not used by the portal code | empty |

### frontend/.env
| Variable | Value |
|---|---|
| REACT_APP_BACKEND_URL | `http://localhost:8001` |

## 5. Data / seed
On startup the backend seeds everything idempotently: the cycle, programmes, policies, staff for each role, candidates for every stage, interviews, results, Part B and finance cases. To load the data snapshot that ships with the zip instead:
```bash
mongorestore --uri "mongodb://localhost:27017" --nsFrom "<SOURCE_DB>.*" --nsTo "weschool_admissions.*" --gzip --archive=seed/weschool-seed.archive.gz
```
`seed/SOURCE_DB.txt` holds the source database name to use for `<SOURCE_DB>`. Files uploaded in the hosted preview (photos, signatures, documents) are not in the snapshot, so their download links return errors locally. Re-upload them, or start with an empty database so the seed creates fresh records.

To re-seed from scratch, drop the database (`mongosh weschool_admissions --eval "db.dropDatabase()"`) and restart the backend.
To reset only Part B and finance: `PYTHONPATH=backend python backend/tests/reset_phase45.py`, then restart the backend.

## 6. Default logins (seed data, change them before any real use)
- Staff portal `/staff/login`: Super Admin `superadmin@weschool-demo.in` / `SuperAdmin@2026`. Every other role (admissions, verifier, panelist, coordinator, accounts, results, auditor `@weschool-demo.in`) uses `Staff@2026`.
- Accounts step-up tester: `delivered+accounts@resend.dev` / `Staff@2026`
- Candidate portal `/candidate/login`: `candidate01@example.com` … `candidate18@example.com` / `Candidate@2026`
- Full list of seeded stages: `memory/test_credentials.md`

## 7. What depends on Emergent services, and what to do locally
| Feature | Hosted preview | Locally without Emergent keys |
|---|---|---|
| Email OTP and notifications | Real Resend email via `EMERGENT_EMAIL_KEY` | **Console mode**: emails are printed to the backend log and the OTP API returns `debug_code`. Add an Emergent email key to send real email. |
| File uploads (photo, signature, Part B documents, payment proof) | Emergent Object Storage, authorised by `EMERGENT_LLM_KEY` | **Local disk fallback** in `LOCAL_STORAGE_DIR`. It is used automatically when `EMERGENT_LLM_KEY` is empty or `STORAGE_MODE=local`. |
| Stripe test payments | Emergent shared test key `sk_test_emergent...`, routed through the Emergent proxy | Use **your own Stripe test key** (`sk_test_...`). Status polling verifies payments with no webhook needed. With your own key, refunds go to Stripe test mode for real; with the shared key they are MOCKED. |
| WhatsApp OTP | MOCKED unless a Twilio template SID is set | Same: MOCKED with `debug_code` unless you add Twilio credentials and a ContentSid |
| Refund step-up OTP | Real email to the Accounts Operator | Console mode: the code is printed in the backend log and returned as `debug_code` |

## 8. Tests
```bash
cd backend && pytest tests -q     # expects the backend running with the seed data
```
