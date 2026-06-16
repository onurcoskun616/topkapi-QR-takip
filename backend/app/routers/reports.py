"""Aggregate reporting: late/early-leave rankings and absence reports.

Every report here is scoped the same way as ``/api/logs``: a campus director
only ever sees their own campus; hq sees everything (optionally filtered to
one campus). "Late" / "early leave" are computed against each staff member's
*campus* shift hours (``Campus.shift_start`` / ``shift_end``, settable only by
hq) plus a caller-supplied ``threshold_minutes`` grace window.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_manager
from ..models import (
    AttendanceLog,
    AttendanceType,
    Campus,
    LeaveRecord,
    LeaveStatus,
    User,
    UserRole,
    UserStatus,
)
from ..schemas import (
    AbsenceDayEntry,
    AbsenceReasonStat,
    AbsenceSummaryResponse,
    AbsenceTotalEntry,
    EarlyLeaveRankingEntry,
    LateRankingEntry,
)
from ..scoping import scope_campus_id

router = APIRouter(prefix="/api/reports", tags=["reports"])

MAX_REPORT_DAYS = 400


def _validate_range(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_date, start_date'den önce olamaz.")
    if (end_date - start_date).days > MAX_REPORT_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tarih aralığı en fazla {MAX_REPORT_DAYS} gün olabilir.",
        )


def _day_range(start_date: date, end_date: date, exclude_weekends: bool):
    d = start_date
    while d <= end_date:
        if not (exclude_weekends and d.weekday() >= 5):
            yield d
        d += timedelta(days=1)


async def _scoped_active_staff(
    db: AsyncSession, manager: User, campus_id: int | None, user_id: int | None
) -> list[User]:
    scope = scope_campus_id(manager, campus_id)
    stmt = select(User).where(User.role == UserRole.staff, User.status == UserStatus.active)
    if scope is not None:
        stmt = stmt.where(User.campus_id == scope)
    if user_id is not None:
        stmt = stmt.where(User.id == user_id)
    return list((await db.execute(stmt)).scalars().all())


async def _logs_for_staff(
    db: AsyncSession, staff_ids: list[int], start_date: date, end_date: date
) -> list[AttendanceLog]:
    if not staff_ids:
        return []
    tz = ZoneInfo(settings.attendance_timezone)
    start_utc = datetime.combine(start_date, time.min, tzinfo=tz).astimezone(timezone.utc)
    end_utc = datetime.combine(end_date, time.max, tzinfo=tz).astimezone(timezone.utc)
    stmt = select(AttendanceLog).where(
        AttendanceLog.user_id.in_(staff_ids),
        AttendanceLog.scan_time >= start_utc,
        AttendanceLog.scan_time <= end_utc,
    )
    return list((await db.execute(stmt)).scalars().all())


@dataclass
class _DayLogs:
    first_in: datetime | None = None
    last_out: datetime | None = None
    any_log: bool = False


def _group_by_staff_day(logs: list[AttendanceLog], tz: ZoneInfo) -> dict[tuple[int, date], _DayLogs]:
    grouped: dict[tuple[int, date], _DayLogs] = defaultdict(_DayLogs)
    for log in logs:
        local_dt = log.scan_time.astimezone(tz)
        key = (log.user_id, local_dt.date())
        bucket = grouped[key]
        bucket.any_log = True
        if log.type == AttendanceType.IN and (bucket.first_in is None or local_dt < bucket.first_in):
            bucket.first_in = local_dt
        if log.type == AttendanceType.OUT and (bucket.last_out is None or local_dt > bucket.last_out):
            bucket.last_out = local_dt
    return grouped


async def _campus_names_map(db: AsyncSession) -> dict[int, str]:
    rows = await db.execute(select(Campus.id, Campus.name))
    return {cid: name for cid, name in rows.all()}


async def _campus_shift_map(db: AsyncSession) -> dict[int, Campus]:
    rows = await db.execute(select(Campus))
    return {c.id: c for c in rows.scalars().all()}


@router.get("/late", response_model=list[LateRankingEntry])
async def late_ranking(
    start_date: date,
    end_date: date,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    user_id: int | None = None,
    threshold_minutes: int = Query(0, ge=0, le=240, description="Grace period before counting as late"),
    exclude_weekends: bool = True,
    limit: int = Query(50, ge=1, le=700),
):
    """Ranking of staff by how often their first IN of the day is later than
    the campus shift start + grace period."""
    _validate_range(start_date, end_date)
    tz = ZoneInfo(settings.attendance_timezone)
    staff = await _scoped_active_staff(db, manager, campus_id, user_id)
    if not staff:
        return []

    logs = await _logs_for_staff(db, [s.id for s in staff], start_date, end_date)
    grouped = _group_by_staff_day(logs, tz)
    campuses = await _campus_shift_map(db)

    results: list[LateRankingEntry] = []
    for s in staff:
        campus = campuses.get(s.campus_id) if s.campus_id else None
        if campus is None or campus.shift_start is None:
            continue  # no shift configured for this campus — cannot judge lateness
        late_minutes: list[float] = []
        for d in _day_range(start_date, end_date, exclude_weekends):
            bucket = grouped.get((s.id, d))
            if bucket is None or bucket.first_in is None:
                continue
            shift_start_local = datetime.combine(d, campus.shift_start, tzinfo=tz)
            minutes_late = (bucket.first_in - shift_start_local).total_seconds() / 60
            if minutes_late > threshold_minutes:
                late_minutes.append(minutes_late)
        if late_minutes:
            results.append(
                LateRankingEntry(
                    user_id=s.id,
                    full_name=s.full_name,
                    campus_name=campus.name,
                    late_days=len(late_minutes),
                    average_late_minutes=round(sum(late_minutes) / len(late_minutes), 1),
                )
            )

    results.sort(key=lambda r: (-r.late_days, -r.average_late_minutes))
    return results[:limit]


@router.get("/early-leave", response_model=list[EarlyLeaveRankingEntry])
async def early_leave_ranking(
    start_date: date,
    end_date: date,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    user_id: int | None = None,
    threshold_minutes: int = Query(0, ge=0, le=240, description="Grace period before counting as early"),
    exclude_weekends: bool = True,
    limit: int = Query(50, ge=1, le=700),
):
    """Ranking of staff by how often their last OUT of the day is earlier than
    the campus shift end - grace period."""
    _validate_range(start_date, end_date)
    tz = ZoneInfo(settings.attendance_timezone)
    staff = await _scoped_active_staff(db, manager, campus_id, user_id)
    if not staff:
        return []

    logs = await _logs_for_staff(db, [s.id for s in staff], start_date, end_date)
    grouped = _group_by_staff_day(logs, tz)
    campuses = await _campus_shift_map(db)

    results: list[EarlyLeaveRankingEntry] = []
    for s in staff:
        campus = campuses.get(s.campus_id) if s.campus_id else None
        if campus is None or campus.shift_end is None:
            continue
        early_minutes: list[float] = []
        for d in _day_range(start_date, end_date, exclude_weekends):
            bucket = grouped.get((s.id, d))
            if bucket is None or bucket.last_out is None:
                continue
            shift_end_local = datetime.combine(d, campus.shift_end, tzinfo=tz)
            minutes_early = (shift_end_local - bucket.last_out).total_seconds() / 60
            if minutes_early > threshold_minutes:
                early_minutes.append(minutes_early)
        if early_minutes:
            results.append(
                EarlyLeaveRankingEntry(
                    user_id=s.id,
                    full_name=s.full_name,
                    campus_name=campus.name,
                    early_leave_days=len(early_minutes),
                    average_early_minutes=round(sum(early_minutes) / len(early_minutes), 1),
                )
            )

    results.sort(key=lambda r: (-r.early_leave_days, -r.average_early_minutes))
    return results[:limit]


async def _compute_absences(
    db: AsyncSession,
    manager: User,
    start_date: date,
    end_date: date,
    campus_id: int | None,
    user_id: int | None,
    exclude_weekends: bool,
) -> list[AbsenceDayEntry]:
    _validate_range(start_date, end_date)
    tz = ZoneInfo(settings.attendance_timezone)
    staff = await _scoped_active_staff(db, manager, campus_id, user_id)
    if not staff:
        return []

    days = list(_day_range(start_date, end_date, exclude_weekends))
    if len(staff) * max(len(days), 1) > 8000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sonuç kümesi çok büyük; tarih aralığını veya kampüs/personel filtresini daraltın.",
        )

    logs = await _logs_for_staff(db, [s.id for s in staff], start_date, end_date)
    present_days = {(log.user_id, log.scan_time.astimezone(tz).date()) for log in logs}

    leave_rows = await db.execute(
        select(LeaveRecord).where(
            LeaveRecord.user_id.in_([s.id for s in staff]),
            LeaveRecord.status == LeaveStatus.active,
            LeaveRecord.start_date <= end_date,
            LeaveRecord.end_date >= start_date,
        )
    )
    leaves_by_staff: dict[int, list[LeaveRecord]] = defaultdict(list)
    for leave in leave_rows.scalars().all():
        leaves_by_staff[leave.user_id].append(leave)

    names = await _campus_names_map(db)

    entries: list[AbsenceDayEntry] = []
    for s in staff:
        staff_leaves = leaves_by_staff.get(s.id, [])
        for d in days:
            if (s.id, d) in present_days:
                continue
            covering = next((lv for lv in staff_leaves if lv.start_date <= d <= lv.end_date), None)
            entries.append(
                AbsenceDayEntry(
                    user_id=s.id,
                    full_name=s.full_name,
                    campus_name=names.get(s.campus_id) if s.campus_id else None,
                    date=d,
                    status=covering.leave_type if covering else "unresolved",
                    leave_record_id=covering.id if covering else None,
                )
            )
    entries.sort(key=lambda e: (e.date, e.full_name))
    return entries


@router.get("/absences", response_model=list[AbsenceDayEntry])
async def absence_detail(
    start_date: date,
    end_date: date,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    user_id: int | None = None,
    exclude_weekends: bool = True,
):
    """Every (staff, day) with zero scans in the range — labelled with the
    covering leave type, or ``unresolved`` if no status has been entered.
    Days are never silently omitted: an absence without a leave record always
    shows up here as ``unresolved`` so it can't go unnoticed."""
    return await _compute_absences(db, manager, start_date, end_date, campus_id, user_id, exclude_weekends)


@router.get("/absence-summary", response_model=AbsenceSummaryResponse)
async def absence_summary(
    start_date: date,
    end_date: date,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    exclude_weekends: bool = True,
):
    """Aggregate absence statistics: totals by reason type, and a per-staff
    ranking of most-absent staff (with a reason breakdown each)."""
    entries = await _compute_absences(db, manager, start_date, end_date, campus_id, None, exclude_weekends)

    by_reason_days: dict[str, int] = defaultdict(int)
    by_reason_staff: dict[str, set[int]] = defaultdict(set)
    by_staff: dict[int, AbsenceTotalEntry] = {}
    unresolved_count = 0

    for e in entries:
        if e.status == "unresolved":
            unresolved_count += 1
        else:
            by_reason_days[e.status] += 1
            by_reason_staff[e.status].add(e.user_id)

        if e.user_id not in by_staff:
            by_staff[e.user_id] = AbsenceTotalEntry(
                user_id=e.user_id,
                full_name=e.full_name,
                campus_name=e.campus_name,
                absent_days=0,
                unresolved_days=0,
                by_reason={},
            )
        total = by_staff[e.user_id]
        total.absent_days += 1
        if e.status == "unresolved":
            total.unresolved_days += 1
        else:
            total.by_reason[e.status] = total.by_reason.get(e.status, 0) + 1

    by_reason = [
        AbsenceReasonStat(leave_type=reason, day_count=count, staff_count=len(by_reason_staff[reason]))
        for reason, count in sorted(by_reason_days.items(), key=lambda kv: -kv[1])
    ]
    totals = sorted(by_staff.values(), key=lambda t: -t.absent_days)

    return AbsenceSummaryResponse(
        start_date=start_date,
        end_date=end_date,
        by_reason=by_reason,
        totals_by_staff=totals,
        unresolved_count=unresolved_count,
    )


@router.get("/export.xlsx", response_class=StreamingResponse)
async def export_reports_xlsx(
    start_date: date,
    end_date: date,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    threshold_minutes: int = Query(0, ge=0, le=240),
    exclude_weekends: bool = True,
):
    """One workbook with a sheet each for late/early-leave rankings and the
    absence detail + summary, for the given date range and scope."""
    late = await late_ranking(
        start_date, end_date, manager, db, campus_id, None, threshold_minutes, exclude_weekends, 700
    )
    early = await early_leave_ranking(
        start_date, end_date, manager, db, campus_id, None, threshold_minutes, exclude_weekends, 700
    )
    absences = await _compute_absences(db, manager, start_date, end_date, campus_id, None, exclude_weekends)
    summary = await absence_summary(start_date, end_date, manager, db, campus_id, exclude_weekends)

    wb = Workbook()

    ws = wb.active
    ws.title = "Geç Kalmalar"
    ws.append(["Personel", "Kampüs", "Geç Kaldığı Gün Sayısı", "Ortalama Geç Kalma (dk)"])
    for r in late:
        ws.append([r.full_name, r.campus_name or "", r.late_days, r.average_late_minutes])

    ws2 = wb.create_sheet("Erken Çıkışlar")
    ws2.append(["Personel", "Kampüs", "Erken Çıktığı Gün Sayısı", "Ortalama Erken Çıkma (dk)"])
    for r in early:
        ws2.append([r.full_name, r.campus_name or "", r.early_leave_days, r.average_early_minutes])

    ws3 = wb.create_sheet("Devamsızlık Detay")
    ws3.append(["Personel", "Kampüs", "Tarih", "Durum"])
    for e in absences:
        ws3.append([e.full_name, e.campus_name or "", e.date.isoformat(), e.status])

    ws4 = wb.create_sheet("Devamsızlık Özeti")
    ws4.append(["İzin/Durum Türü", "Toplam Gün", "Personel Sayısı"])
    for r in summary.by_reason:
        ws4.append([r.leave_type, r.day_count, r.staff_count])
    ws4.append([])
    ws4.append(["Durum Girilmemiş Gün Sayısı", summary.unresolved_count])
    ws4.append([])
    ws4.append(["Personel", "Kampüs", "Toplam Devamsız Gün", "Durum Girilmemiş Gün"])
    for t in summary.totals_by_staff:
        ws4.append([t.full_name, t.campus_name or "", t.absent_days, t.unresolved_days])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"raporlar_{start_date.isoformat()}_{end_date.isoformat()}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
