"""Kiosk QR token generation.

The kiosk polls this endpoint (or relies on the returned ``ttl_seconds``) to
render a fresh, expiring QR every 15 seconds. No authentication is required to
*display* a code because the code itself is useless without a logged-in teacher
scanning it; the secret never leaves the server.
"""
from datetime import datetime, timezone

from fastapi import APIRouter

from ..config import settings
from ..schemas import QrTokenResponse
from ..security import create_qr_token

router = APIRouter(prefix="/api/qr", tags=["qr"])


@router.get("/token", response_model=QrTokenResponse)
async def get_qr_token():
    """Return a fresh QR token valid for ``QR_TOKEN_TTL_SECONDS`` (default 15s)."""
    data = create_qr_token()
    return QrTokenResponse(
        token=data["token"],
        issued_at=data["issued_at"],
        expires_at=data["expires_at"],
        ttl_seconds=settings.qr_token_ttl_seconds,
        server_time=datetime.now(timezone.utc),
    )
