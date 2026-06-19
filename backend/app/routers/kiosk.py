"""Kiosk-facing feed that the tablet polls while it shows the QR code.

The scan happens on the teacher's phone (the QR is read from the tablet and
``POST /api/scan`` comes from the phone), so the tablet itself never sees the
result. To confirm a scan *on the tablet* — a green "Giriş/Çıkış başarılı"
check, plus a full-screen birthday celebration when relevant — the kiosk polls
this endpoint for the campus's most recent successful QR scans.

The kiosk has no auth and no campus identity of its own, so it passes its
``campus_id`` (from the tablet URL, e.g. ``?campus=3``). Only valid ``qr_scan``
rows from the last few seconds are returned, so a tablet that powers on later
never replays old scans; the kiosk also de-dupes by ``log_id`` to show each
scan once. A scan is flagged ``birthday`` when it is the staff member's first
IN of the day and today is their birthday — the kiosk shows the celebration
instead of a plain confirmation for those.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from sqlalchemy import or_

from ..config import settings
from ..database import get_db
from ..models import (
    Announcement,
    AttendanceLog,
    AttendanceSource,
    AttendanceStatus,
    AttendanceType,
    User,
    UserRole,
    UserStatus,
    ensure_aware,
)
from ..schemas import (
    KioskAnnouncement,
    KioskAnnouncementsResponse,
    RecentScan,
    RecentScansResponse,
)
from ..services import day_bounds_utc
from .announcements import image_path, is_visible, video_path

router = APIRouter(prefix="/api/kiosk", tags=["kiosk"])

# Only surface scans from the last few seconds, so a tablet that loads later in
# the day doesn't suddenly replay old confirmations. The kiosk polls fast
# (~1.5s) and de-dupes by log_id, so this window only needs to comfortably
# exceed the poll interval plus any clock skew.
RECENT_SCAN_WINDOW_SECONDS = 12


@router.get("/recent-scans", response_model=RecentScansResponse)
async def recent_scans(
    campus_id: int = Query(..., description="The kiosk's campus (from the tablet URL ?campus=)"),
    db: AsyncSession = Depends(get_db),
):
    tz = ZoneInfo(settings.attendance_timezone)
    now_utc = datetime.now(timezone.utc)
    today_local = now_utc.astimezone(tz).date()
    start_utc, end_utc = day_bounds_utc(today_local)
    window_start = now_utc.timestamp() - RECENT_SCAN_WINDOW_SECONDS

    # Active staff of this campus, so we can attach names and spot birthdays.
    staff_rows = await db.execute(
        select(User).where(
            User.campus_id == campus_id,
            User.role == UserRole.staff,
            User.status == UserStatus.active,
        )
    )
    staff = {s.id: s for s in staff_rows.scalars().all()}
    if not staff:
        return RecentScansResponse(scans=[])

    birthday_ids = {
        sid
        for sid, s in staff.items()
        if s.birth_date is not None
        and s.birth_date.month == today_local.month
        and s.birth_date.day == today_local.day
    }

    # Today's valid QR scans for this campus's staff (manual director entries
    # and the nightly auto-close are excluded — nobody is standing at the
    # tablet for those).
    log_rows = await db.execute(
        select(AttendanceLog)
        .where(
            AttendanceLog.user_id.in_(staff.keys()),
            AttendanceLog.source == AttendanceSource.qr_scan,
            AttendanceLog.status == AttendanceStatus.valid,
            AttendanceLog.scan_time >= start_utc,
            AttendanceLog.scan_time <= end_utc,
        )
        .order_by(AttendanceLog.scan_time.asc())
    )
    todays_logs = list(log_rows.scalars().all())

    # The first IN of the day for each birthday staff member — that exact scan
    # earns the celebration (a later IN after an OUT does not).
    birthday_first_in: set[int] = set()
    for log in todays_logs:
        if log.user_id in birthday_ids and log.type == AttendanceType.IN:
            birthday_first_in.add(log.id)
            birthday_ids.discard(log.user_id)  # only the earliest IN counts

    scans: list[RecentScan] = []
    for log in todays_logs:
        scan_utc = ensure_aware(log.scan_time)
        if scan_utc.timestamp() < window_start:
            continue  # too old to confirm on the tablet now
        scans.append(
            RecentScan(
                log_id=log.id,
                user_id=log.user_id,
                full_name=staff[log.user_id].full_name,
                type=log.type,
                scan_time=scan_utc,
                birthday=log.id in birthday_first_in,
            )
        )

    scans.sort(key=lambda s: s.scan_time)
    return RecentScansResponse(scans=scans)


@router.get("/announcements", response_model=KioskAnnouncementsResponse)
async def kiosk_announcements(
    campus_id: int = Query(..., description="The kiosk's campus (from the tablet URL ?campus=)"),
    db: AsyncSession = Depends(get_db),
):
    """Public feed of the notices this campus's kiosk should display right now.

    Returns the campus's own notices plus the all-campus ones, filtered to those
    currently active and within their schedule window. Oldest first so a steady
    rotation order stays stable as new notices are added.
    """
    now_utc = datetime.now(timezone.utc)
    rows = await db.execute(
        select(Announcement)
        .where(
            or_(
                Announcement.campus_id == campus_id,
                Announcement.campus_id.is_(None),
            )
        )
        .order_by(Announcement.created_at.asc())
    )
    visible = [a for a in rows.scalars().all() if is_visible(a, now_utc)]
    return KioskAnnouncementsResponse(
        announcements=[
            KioskAnnouncement(
                id=a.id,
                title=a.title,
                body=a.body,
                image_url=image_path(a.id) if a.image_data is not None else None,
                video_url=video_path(a.id) if a.video_data is not None else None,
            )
            for a in visible
        ]
    )
