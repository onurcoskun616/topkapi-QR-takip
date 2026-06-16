"""Business logic shared by routes and the scheduler."""
import re
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import (
    AttendanceLog,
    AttendanceStatus,
    AttendanceType,
    LeaveRecord,
    LeaveStatus,
)

# Suggested leave/absence reasons shown in the admin UI dropdown. Free text is
# still accepted ("ve benzeri" — the list is explicitly open-ended), so this is
# guidance, not a database-level enum.
SUGGESTED_LEAVE_TYPES: list[str] = [
    "Sağlık raporu",
    "Ücretli izin",
    "Ücretsiz izin",
    "Evlilik izni",
    "Babalık izni",
    "Gebelik/Doğum izni",
    "Mazeret izni",
]


def normalize_phone(raw: str) -> str:
    """Canonicalise a phone number so the same line always maps to one identity.

    Strips spaces/dashes/parentheses, keeps a single leading ``+``, and converts
    a Turkish national ``0XXXXXXXXXX`` to ``+90XXXXXXXXXX`` so "0532…" and
    "+90 532…" are treated as the same person.
    """
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.startswith("0") and len(digits) == 11:  # 05XXXXXXXXX
        digits = "+90" + digits[1:]
    elif digits.startswith("90") and len(digits) == 12:
        digits = "+" + digits
    return digits


def day_bounds_utc(local_date: date) -> tuple[datetime, datetime]:
    """Return [start, end] of the given local calendar date, expressed in UTC."""
    tz = ZoneInfo(settings.attendance_timezone)
    start_local = datetime.combine(local_date, time.min, tzinfo=tz)
    end_local = datetime.combine(local_date, time.max, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def local_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    """Return [start, end] of the current local calendar day, expressed in UTC.

    Attendance "day" is defined in ``ATTENDANCE_TIMEZONE`` (e.g. Europe/Istanbul)
    but all rows are stored/queried in UTC.
    """
    tz = ZoneInfo(settings.attendance_timezone)
    return day_bounds_utc(now_utc.astimezone(tz).date())


async def get_last_log_for_day(
    db: AsyncSession, user_id: int, local_date: date
) -> AttendanceLog | None:
    """Most recent attendance log (any source) for the user on a given local day."""
    start_utc, end_utc = day_bounds_utc(local_date)
    result = await db.execute(
        select(AttendanceLog)
        .where(
            AttendanceLog.user_id == user_id,
            AttendanceLog.scan_time >= start_utc,
            AttendanceLog.scan_time <= end_utc,
        )
        .order_by(AttendanceLog.scan_time.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_last_log_today(
    db: AsyncSession, user_id: int, now_utc: datetime
) -> AttendanceLog | None:
    """Most recent attendance log for the user within the current local day."""
    tz = ZoneInfo(settings.attendance_timezone)
    return await get_last_log_for_day(db, user_id, now_utc.astimezone(tz).date())


def next_attendance_type(last_log: AttendanceLog | None) -> AttendanceType:
    """Toggle rule:

    * no record today, or last record is OUT  -> IN
    * last record today is IN                  -> OUT
    """
    if last_log is None or last_log.type == AttendanceType.OUT:
        return AttendanceType.IN
    return AttendanceType.OUT


async def record_scan(
    db: AsyncSession, user_id: int, now_utc: datetime
) -> AttendanceLog:
    """Create the next toggled attendance log for the user. Caller commits."""
    last_log = await get_last_log_today(db, user_id, now_utc)
    log = AttendanceLog(
        user_id=user_id,
        scan_time=now_utc,
        type=next_attendance_type(last_log),
        status=AttendanceStatus.valid,
    )
    db.add(log)
    return log


async def get_active_leave_for_day(
    db: AsyncSession, user_id: int, local_date: date
) -> LeaveRecord | None:
    """The active leave/absence record (if any) covering the given local date."""
    result = await db.execute(
        select(LeaveRecord)
        .where(
            LeaveRecord.user_id == user_id,
            LeaveRecord.status == LeaveStatus.active,
            LeaveRecord.start_date <= local_date,
            LeaveRecord.end_date >= local_date,
        )
        .order_by(LeaveRecord.start_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
