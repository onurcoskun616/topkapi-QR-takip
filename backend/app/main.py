"""FastAPI application entrypoint for the Topkapı QR Attendance backend."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .bootstrap import (
    create_tables,
    ensure_bootstrap_admin,
    ensure_campuses,
    ensure_schema_upgrades,
)
from .config import settings
from .deps import get_current_hq
from .routers import (
    auth,
    campuses,
    holidays,
    kiosk,
    leaves,
    logs,
    management,
    qr,
    reports,
    scan,
)
from .tasks.scheduler import (
    auto_close_open_attendances,
    shutdown_scheduler,
    start_scheduler,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await ensure_schema_upgrades()
    await ensure_campuses()
    await ensure_bootstrap_admin()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(
    title="Topkapı Okulları — Dinamik QR Yoklama API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(campuses.router)
app.include_router(management.router)
app.include_router(qr.router)
app.include_router(scan.router)
app.include_router(logs.router)
app.include_router(leaves.router)
app.include_router(holidays.router)
app.include_router(reports.router)
app.include_router(kiosk.router)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "server_time": datetime.now(timezone.utc)}


# Admin utility to trigger the nightly close on demand (testing / manual reset).
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


@admin_router.post("/run-auto-close", dependencies=[Depends(get_current_hq)])
async def run_auto_close():
    closed = await auto_close_open_attendances()
    return {"auto_closed": closed}


app.include_router(admin_router)
