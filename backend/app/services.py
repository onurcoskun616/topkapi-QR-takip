"""Business logic shared by routes and the scheduler."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import AttendanceLog, AttendanceStatus, AttendanceType


def local_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    """Return [start, end) of the current local calendar day, expressed in UTC.

    Attendance "day" is defined in ``ATTENDANCE_TIMEZONE`` (e.g. Europe/Istanbul)
    but all rows are stored/queried in UTC.
    """
    tz = ZoneInfo(settings.attendance_timezone)
    local_now = now_utc.astimezone(tz)
    start_local = datetime.combine(local_now.date(), time.min, tzinfo=tz)
    end_local = datetime.combine(local_now.date(), time.max, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def get_last_log_today(
    db: AsyncSession, user_id: int, now_utc: datetime
) -> AttendanceLog | None:
    """Most recent attendance log for the user within the current local day."""
    start_utc, end_utc = local_day_bounds_utc(now_utc)
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
