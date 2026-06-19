"""Business logic shared by routes and the scheduler."""
import math
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


# Default working week when a staff member has no per-person schedule set:
# Monday–Friday as ISO weekday numbers (1=Monday … 7=Sunday).
DEFAULT_WORKING_DAYS: frozenset[int] = frozenset({1, 2, 3, 4, 5})
ALL_WEEK_DAYS: frozenset[int] = frozenset({1, 2, 3, 4, 5, 6, 7})


def parse_working_days(raw: str | None) -> set[int] | None:
    """Parse the stored ``"1,2,3,4,5"`` form into a set of ISO weekday numbers.

    Returns ``None`` when nothing is configured (the caller then falls back to
    its weekday default). Ignores blanks and out-of-range tokens defensively.
    """
    if not raw:
        return None
    days: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            n = int(token)
        except ValueError:
            continue
        if 1 <= n <= 7:
            days.add(n)
    return days or None


def format_working_days(days: list[int] | set[int] | None) -> str | None:
    """Serialise ISO weekday numbers into the stored ``"1,2,3,4,5"`` form.

    An empty/None list clears the schedule (stored as ``NULL`` → default week).
    """
    if not days:
        return None
    cleaned = sorted({int(d) for d in days if 1 <= int(d) <= 7})
    return ",".join(str(d) for d in cleaned) if cleaned else None


def effective_working_days(raw: str | None, exclude_weekends_default: bool) -> set[int]:
    """The set of ISO weekday numbers a staff member is expected to work.

    Uses their per-person schedule when set; otherwise falls back to Mon–Fri
    (``exclude_weekends_default`` True) or the whole week.
    """
    parsed = parse_working_days(raw)
    if parsed is not None:
        return parsed
    return set(DEFAULT_WORKING_DAYS if exclude_weekends_default else ALL_WEEK_DAYS)


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


_TR_MOBILE_RE = re.compile(r"^\+905\d{9}$")


def validate_phone(normalized: str) -> bool:
    """True if a *normalized* phone is a well-formed Turkish mobile number
    (``+90`` + 10 digits, starting with ``5``)."""
    return bool(_TR_MOBILE_RE.fullmatch(normalized))


def describe_phone_error(normalized: str) -> str | None:
    """A Turkish, length-aware warning for a malformed phone, or ``None`` if it
    is a valid Turkish mobile number. Distinguishes "too few" / "too many"
    digits so the registration form can tell the user exactly what's wrong."""
    if validate_phone(normalized):
        return None
    local = normalized[3:] if normalized.startswith("+90") else normalized.lstrip("+0")
    if len(local) < 10:
        return f"Telefon numarası eksik: {len(local)} hane girildi, 10 hane olmalı (05XX XXX XX XX)."
    if len(local) > 10:
        return f"Telefon numarası fazla karakter içeriyor: {len(local)} hane girildi, 10 hane olmalı (05XX XXX XX XX)."
    return "Geçersiz telefon numarası. 05XX XXX XX XX biçiminde bir cep telefonu numarası girin."


def validate_tc_kimlik(value: str) -> bool:
    """Standard Turkish TC Kimlik No checksum (11 digits, first digit non-zero):

    * digit 10 = ((sum of digits 1,3,5,7,9) * 7 − sum of digits 2,4,6,8) mod 10
    * digit 11 = (sum of digits 1..10) mod 10
    """
    if not value or not value.isdigit() or len(value) != 11 or value[0] == "0":
        return False
    d = [int(c) for c in value]
    odd_sum = d[0] + d[2] + d[4] + d[6] + d[8]
    even_sum = d[1] + d[3] + d[5] + d[7]
    if (odd_sum * 7 - even_sum) % 10 != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


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
    db: AsyncSession, user_id: int, now_utc: datetime, kiosk_id: str | None = None
) -> AttendanceLog:
    """Create the next toggled attendance log for the user. Caller commits."""
    last_log = await get_last_log_today(db, user_id, now_utc)
    log = AttendanceLog(
        user_id=user_id,
        scan_time=now_utc,
        type=next_attendance_type(last_log),
        status=AttendanceStatus.valid,
        kiosk_id=kiosk_id,
    )
    db.add(log)
    return log


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lng points, in metres."""
    r = 6371000.0  # Earth radius (m)
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


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
