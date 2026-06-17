"""The /api/scan endpoint — the heart of the attendance flow.

Flow:
  1. Teacher is authenticated via their own login JWT (Authorization header).
  2. Body carries the QR token read from the kiosk screen.
  3. Server validates QR token signature + 15s expiry (server clock only).
  4. Replay protection: the QR token's jti can be consumed exactly once.
  5. Toggle: decide IN/OUT from the user's last log *today* and persist it.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from jose import ExpiredSignatureError, JWTError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_active_staff
from ..models import AttendanceType, User, UsedQrToken
from ..schemas import ScanRequest, ScanResponse
from ..security import decode_qr_token
from ..services import get_active_leave_for_day, record_scan

router = APIRouter(prefix="/api", tags=["scan"])

_MESSAGES = {
    AttendanceType.IN: "Giriş başarılı",
    AttendanceType.OUT: "Çıkış başarılı",
}


@router.post("/scan", response_model=ScanResponse)
async def scan(
    payload: ScanRequest,
    current: User = Depends(get_current_active_staff),
    db: AsyncSession = Depends(get_db),
):
    # --- 0. Blocked while an active leave/absence record covers today -------
    today_local = datetime.now(timezone.utc).astimezone(
        ZoneInfo(settings.attendance_timezone)
    ).date()
    leave = await get_active_leave_for_day(db, current.id, today_local)
    if leave is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Bugün için '{leave.leave_type}' durumu kayıtlı. "
                "Bir hata olduğunu düşünüyorsanız kampüs müdürünüze başvurun."
            ),
        )

    # --- 1. Validate the QR token (signature + expiry on the SERVER clock) ---
    try:
        qr = decode_qr_token(payload.qr_token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="QR kodun süresi doldu. Lütfen yeni kodu okutun.",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz QR kod.",
        )

    jti = qr.get("jti")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz QR kod."
        )

    # --- 2. Replay protection: consume the jti exactly once ------------------
    db.add(UsedQrToken(jti=jti))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu QR kod zaten kullanıldı. Lütfen ekrandaki yeni kodu okutun.",
        )

    # --- 3. Toggle IN/OUT based on today's last record -----------------------
    now_utc = datetime.now(timezone.utc)
    log = await record_scan(db, current.id, now_utc)
    await db.commit()
    await db.refresh(log)

    return ScanResponse(
        success=True,
        type=log.type,
        message=_MESSAGES[log.type],
        scan_time=log.scan_time,
        user_full_name=current.full_name,
    )
