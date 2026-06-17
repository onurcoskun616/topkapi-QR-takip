"""Kiosk-facing helpers that the tablet polls while it shows the QR code.

Birthday celebrations: when a staff member whose birthday is *today* scans
their **first IN of the day** via the kiosk QR, the tablet should congratulate
them. The kiosk has no auth and no campus identity of its own, so it passes its
``campus_id`` (from the tablet URL, e.g. ``?campus=3``) and polls this endpoint.
Only first-IN ``qr_scan`` rows from the last few seconds are returned, so a
tablet that powers on later in the day never replays a stale celebration; the
kiosk also de-dupes by ``log_id`` to show each person at most once.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from ..config import settings
from ..database import get_db
from ..models import (
    AttendanceLog,
    AttendanceSource,
    AttendanceType,
    User,
    UserRole,
    UserStatus,
    ensure_aware,
)
from ..schemas import BirthdayCelebration, CelebrationsResponse
from ..services import day_bounds_utc

router = APIRouter(prefix="/api/kiosk", tags=["kiosk"])

# Only celebrate a first-IN scan that happened within this many seconds, so a
# tablet that loads mid-morning doesn't suddenly replay an old birthday scan.
CELEBRATION_WINDOW_SECONDS = 90


@router.get("/celebrations", response_model=CelebrationsResponse)
async def celebrations(
    campus_id: int = Query(..., description="The kiosk's campus (from the tablet URL ?campus=)"),
    db: AsyncSession = Depends(get_db),
):
    tz = ZoneInfo(settings.attendance_timezone)
    now_utc = datetime.now(timezone.utc)
    today_local = now_utc.astimezone(tz).date()
    start_utc, end_utc = day_bounds_utc(today_local)

    # Active staff of this campus who have a birthday recorded.
    staff_rows = await db.execute(
        select(User).where(
            User.campus_id == campus_id,
            User.role == UserRole.staff,
            User.status == UserStatus.active,
            User.birth_date.is_not(None),
        )
    )
    birthday_staff = {
        s.id: s
        for s in staff_rows.scalars().all()
        if s.birth_date.month == today_local.month and s.birth_date.day == today_local.day
    }
    if not birthday_staff:
        return CelebrationsResponse(celebrations=[])

    # All of today's IN scans for those staff, earliest first, so we can pick
    # each person's *first* IN of the day.
    log_rows = await db.execute(
        select(AttendanceLog)
        .where(
            AttendanceLog.user_id.in_(birthday_staff.keys()),
            AttendanceLog.type == AttendanceType.IN,
            AttendanceLog.scan_time >= start_utc,
            AttendanceLog.scan_time <= end_utc,
        )
        .order_by(AttendanceLog.scan_time.asc())
    )

    first_in: dict[int, AttendanceLog] = {}
    for log in log_rows.scalars().all():
        first_in.setdefault(log.user_id, log)

    results: list[BirthdayCelebration] = []
    for user_id, log in first_in.items():
        if log.source != AttendanceSource.qr_scan:
            continue  # a director's manual entry isn't someone scanning in person
        scan_utc = ensure_aware(log.scan_time)
        if (now_utc - scan_utc).total_seconds() > CELEBRATION_WINDOW_SECONDS:
            continue
        staff = birthday_staff[user_id]
        results.append(
            BirthdayCelebration(
                user_id=user_id,
                full_name=staff.full_name,
                log_id=log.id,
                scan_time=scan_utc,
            )
        )

    results.sort(key=lambda c: c.scan_time)
    return CelebrationsResponse(celebrations=results)
