"""Kiosk QR token generation.

The kiosk polls this endpoint (or relies on the returned ``ttl_seconds``) to
render a fresh, expiring QR every 15 seconds. No authentication is required to
*display* a code because the code itself is useless without a logged-in teacher
scanning it; the secret never leaves the server.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import UsedQrToken
from ..schemas import QrTokenResponse, QrTokenStatusResponse
from ..security import create_qr_token

router = APIRouter(prefix="/api/qr", tags=["qr"])


@router.get("/token", response_model=QrTokenResponse)
async def get_qr_token(campus_id: int | None = None, kiosk_id: str | None = None):
    """Return a fresh QR token valid for ``QR_TOKEN_TTL_SECONDS`` (default 15s).

    The kiosk passes its own ``campus_id`` (from the tablet URL ``?campus=``) so
    the code is bound to this campus; a teacher from another campus scanning it
    is then refused. Omitting it keeps the old, unbound behaviour.

    ``kiosk_id`` is a per-tablet identifier the kiosk generates once and keeps
    (so several tablets at one campus are distinguishable). It rides along on
    the resulting attendance log, letting ``/api/kiosk/recent-scans`` confirm a
    scan only on the tablet whose own code was scanned.
    """
    data = create_qr_token(campus_id, kiosk_id)
    return QrTokenResponse(
        token=data["token"],
        jti=data["jti"],
        issued_at=data["issued_at"],
        expires_at=data["expires_at"],
        ttl_seconds=settings.qr_token_ttl_seconds,
        server_time=datetime.now(timezone.utc),
    )


@router.get("/token/{jti}/status", response_model=QrTokenStatusResponse)
async def get_qr_token_status(jti: str, db: AsyncSession = Depends(get_db)):
    """Has this token already been consumed by a scan?

    Several kiosks can be running at once at the same campus; each shows its
    own independently-generated code, so the same code never appears on two
    screens at the same time. This lets a kiosk notice the *instant* its own
    currently-displayed code is scanned, so it can roll over to a fresh one
    immediately instead of leaving a dead code on screen for the rest of its
    15-second window.
    """
    used = (
        await db.execute(select(UsedQrToken.jti).where(UsedQrToken.jti == jti))
    ).scalar_one_or_none() is not None
    return QrTokenStatusResponse(used=used)
