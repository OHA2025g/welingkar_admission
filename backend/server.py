import asyncio
import logging
import os
import uuid

from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware

from core import client, ensure_indexes
from routes import (admin, admin360, allotment, application, applications_admin, assessments, auth, cancellation, config, finance,
                    interviews, ops, otp, partb, partb_docs, payments, poc, policies, reports, results)
from seed_finance import ensure_finance_indexes, seed_finance
from seed import ensure_auth_indexes, seed
from seed_applications import seed_applications
from seed_interviews import ensure_interview_indexes, seed_interviews
from seed_partb import ensure_partb_indexes, seed_partb
from services.fee_reminders import reminder_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="WeSchool Admissions Portal API", version="0.1.0-phase0",
              openapi_url="/api/openapi.json", docs_url="/api/docs", redoc_url=None)

app.include_router(poc.router)
app.include_router(otp.router)
app.include_router(payments.router)
app.include_router(auth.router)
app.include_router(config.router)
app.include_router(policies.router)
app.include_router(admin.router)
app.include_router(application.router)
app.include_router(applications_admin.router)
app.include_router(interviews.router)
app.include_router(assessments.router)
app.include_router(results.router)
app.include_router(partb.router)
app.include_router(partb_docs.router)
app.include_router(allotment.router)
app.include_router(finance.router)
app.include_router(cancellation.router)
app.include_router(admin360.router)
app.include_router(reports.router)
app.include_router(ops.router)

_reminder_task: asyncio.Task | None = None


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    cid = request.headers.get("x-correlation-id") or uuid.uuid4().hex
    request.state.correlation_id = cid
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ["CORS_ORIGINS"].split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Correlation-ID"],
)


@app.on_event("startup")
async def startup():
    await ensure_indexes()
    await ensure_auth_indexes()
    await poc.seed_sample_application()
    await seed()
    await seed_applications()
    await ensure_interview_indexes()
    await seed_interviews()
    await ensure_partb_indexes()
    await seed_partb()
    await ensure_finance_indexes()
    await seed_finance()
    global _reminder_task
    _reminder_task = asyncio.create_task(reminder_loop())


@app.on_event("shutdown")
async def shutdown():
    if _reminder_task:
        _reminder_task.cancel()
    client.close()
