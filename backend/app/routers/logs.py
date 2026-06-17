"""Attendance log querying, reporting, manual entry and CSV/Excel export.

Scope:
  * Staff see their own history (``/me``).
  * Campus directors see/export their own campus; head office sees every campus
    (optionally filtered to one with ``campus_id``).
"""
import csv
import io
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..config import settings
from ..database import get_db
from ..deps import get_current_active_staff, get_current_manager
from ..models import (
    AttendanceLog,
    AttendanceSource,
    AttendanceType,
    Campus,
    User,
)
from ..schemas import (
    AttendanceLogResponse,
    AttendanceLogWithUser,
    ManualAttendanceCreate,
    MyStatusResponse,
    PresenceEntry,
    TodaySummary,
)
from ..scoping import load_scoped_staff, scope_campus_id
from ..services import (
    day_bounds_utc,
    get_active_leave_for_day,
    get_last_log_for_day,
    local_day_bounds_utc,
    next_attendance_type,
)

router = APIRouter(prefix="/api/logs", tags=["logs"])

_RecordedBy = aliased(User)


def _range_bounds_utc(
    day: date | None, start_date: date | None, end_date: date | None
) -> tuple[datetime, datetime] | None:
    """Resolve the requested filter into a single [start, end] UTC window.

    ``day`` (legacy single-day filter) takes priority; otherwise a
    ``start_date``/``end_date`` range is used when either is given.
    """
    if day is not None:
        return day_bounds_utc(day)
    if start_date is not None or end_date is not None:
        start = start_date or end_date
        end = end_date or start_date
        start_utc, _ = day_bounds_utc(start)
        _, end_utc = day_bounds_utc(end)
        return start_utc, end_utc
    return None


def _filtered_logs_stmt(
    campus_id: int | None,
    user_id: int | None,
    bounds: tuple[datetime, datetime] | None,
    limit: int | None,
) -> Select:
    stmt = (
        select(AttendanceLog, User.full_name, User.phone, Campus.name, _RecordedBy.full_name)
        .join(User, User.id == AttendanceLog.user_id)
        .join(Campus, Campus.id == User.campus_id, isouter=True)
        .join(_RecordedBy, _RecordedBy.id == AttendanceLog.recorded_by_id, isouter=True)
        .order_by(AttendanceLog.scan_time.desc())
    )
    if campus_id is not None:
        stmt = stmt.where(User.campus_id == campus_id)
    if user_id is not None:
        stmt = stmt.where(AttendanceLog.user_id == user_id)
    if bounds is not None:
        start, end = bounds
        stmt = stmt.where(AttendanceLog.scan_time >= start, AttendanceLog.scan_time <= end)
    if limit is not None:
        stmt = stmt.limit(limit)
    return stmt


@router.get("/me", response_model=list[AttendanceLogResponse])
async def my_logs(
    current: User = Depends(get_current_active_staff),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
):
    result = await db.execute(
        select(AttendanceLog)
        .where(AttendanceLog.user_id == current.id)
        .order_by(AttendanceLog.scan_time.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get("/me/status", response_model=MyStatusResponse)
async def my_status(
    current: User = Depends(get_current_active_staff),
    db: AsyncSession = Depends(get_db),
):
    """The staff member's own live state: are they currently 'inside', and (if
    their campus shift has ended) should they be reminded to scan out before
    the nightly auto-close. Powers the PWA check-out reminder."""
    tz = ZoneInfo(settings.attendance_timezone)
    now_utc = datetime.now(timezone.utc)
    today_local = now_utc.astimezone(tz).date()
    last_log = await get_last_log_for_day(db, current.id, today_local)

    currently_in = last_log is not None and last_log.type == AttendanceType.IN
    should_check_out = False
    minutes_overdue: int | None = None
    if currently_in and current.campus_id is not None:
        campus = await db.get(Campus, current.campus_id)
        if campus is not None and campus.shift_end is not None:
            shift_end_utc = datetime.combine(
                today_local, campus.shift_end, tzinfo=tz
            ).astimezone(timezone.utc)
            overdue = (now_utc - shift_end_utc).total_seconds() / 60
            if overdue > 0:
                should_check_out = True
                minutes_overdue = int(overdue)

    return MyStatusResponse(
        currently_in=currently_in,
        since=last_log.scan_time if currently_in else None,
        should_check_out=should_check_out,
        minutes_overdue=minutes_overdue,
    )


@router.get("", response_model=list[AttendanceLogWithUser])
async def all_logs(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    user_id: int | None = None,
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    day: date | None = Query(None, description="Filter to a single local day (YYYY-MM-DD)"),
    start_date: date | None = Query(None, description="Range filter start (inclusive)"),
    end_date: date | None = Query(None, description="Range filter end (inclusive)"),
    limit: int = Query(200, ge=1, le=2000),
):
    scope = scope_campus_id(manager, campus_id)
    bounds = _range_bounds_utc(day, start_date, end_date)
    result = await db.execute(_filtered_logs_stmt(scope, user_id, bounds, limit))
    return [
        AttendanceLogWithUser(
            id=log.id,
            user_id=log.user_id,
            scan_time=log.scan_time,
            type=log.type,
            status=log.status,
            source=log.source,
            note=log.note,
            user_full_name=full_name,
            campus_name=campus_name,
            recorded_by_name=recorded_by_name,
        )
        for log, full_name, _phone, campus_name, recorded_by_name in result.all()
    ]


def _csv_rows(rows, tz: ZoneInfo):
    for log, full_name, phone, campus_name, recorded_by_name in rows:
        scan_utc = log.scan_time.astimezone(timezone.utc)
        yield [
            log.id,
            log.user_id,
            full_name,
            phone or "",
            campus_name or "",
            log.type.value,
            log.status.value,
            "QR okuma" if log.source == AttendanceSource.qr_scan else "Müdür girişi",
            recorded_by_name or "",
            log.note or "",
            scan_utc.isoformat(),
            scan_utc.astimezone(tz).isoformat(),
        ]


_COLUMNS = [
    "log_id",
    "user_id",
    "full_name",
    "phone",
    "campus",
    "type",
    "status",
    "source",
    "recorded_by",
    "note",
    "scan_time_utc",
]


def _header_row() -> list[str]:
    return _COLUMNS + [f"scan_time_local ({settings.attendance_timezone})"]


@router.get("/export", response_class=StreamingResponse)
async def export_logs_csv(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    user_id: int | None = None,
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    day: date | None = Query(None, description="Filter to a single local day (YYYY-MM-DD)"),
    start_date: date | None = Query(None, description="Range filter start (inclusive)"),
    end_date: date | None = Query(None, description="Range filter end (inclusive)"),
):
    """Stream filtered attendance logs as a CSV file.

    Timestamps are emitted in both UTC and the configured local timezone so the
    report is unambiguous regardless of who opens it.
    """
    tz = ZoneInfo(settings.attendance_timezone)
    scope = scope_campus_id(manager, campus_id)
    bounds = _range_bounds_utc(day, start_date, end_date)
    result = await db.execute(_filtered_logs_stmt(scope, user_id, bounds, limit=None))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_header_row())
    for row in _csv_rows(result.all(), tz):
        writer.writerow(row)

    buffer.seek(0)
    filename = f"attendance_{day.isoformat() if day else 'all'}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export.xlsx", response_class=StreamingResponse)
async def export_logs_xlsx(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    user_id: int | None = None,
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    day: date | None = Query(None, description="Filter to a single local day (YYYY-MM-DD)"),
    start_date: date | None = Query(None, description="Range filter start (inclusive)"),
    end_date: date | None = Query(None, description="Range filter end (inclusive)"),
):
    """Same data as ``/export`` but as an .xlsx workbook."""
    tz = ZoneInfo(settings.attendance_timezone)
    scope = scope_campus_id(manager, campus_id)
    bounds = _range_bounds_utc(day, start_date, end_date)
    result = await db.execute(_filtered_logs_stmt(scope, user_id, bounds, limit=None))

    wb = Workbook()
    ws = wb.active
    ws.title = "Kayıtlar"
    ws.append(_header_row())
    for row in _csv_rows(result.all(), tz):
        ws.append(row)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"attendance_{day.isoformat() if day else 'all'}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/manual", response_model=AttendanceLogWithUser, status_code=status.HTTP_201_CREATED)
async def create_manual_attendance(
    payload: ManualAttendanceCreate,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Director/hq gap-fill entry for a staff member who couldn't scan (phone
    died, forgot to scan). Strictly additive — there is no endpoint that edits
    or deletes a real ``qr_scan`` row, so this can never override real scan
    data, only fill a genuine gap.
    """
    staff = await load_scoped_staff(db, manager, payload.user_id)

    tz = ZoneInfo(settings.attendance_timezone)
    occurred_local = datetime.combine(payload.date, payload.time, tzinfo=tz)
    occurred_utc = occurred_local.astimezone(timezone.utc)
    if occurred_utc > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gelecek bir tarih/saat için kayıt girilemez.",
        )

    leave = await get_active_leave_for_day(db, staff.id, payload.date)
    if leave is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Bu personel {payload.date.isoformat()} için '{leave.leave_type}' "
                "olarak işaretli. Önce izin kaydını düzeltin."
            ),
        )

    last_log = await get_last_log_for_day(db, staff.id, payload.date)
    expected = next_attendance_type(last_log)
    if payload.type != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Bu gün için sıradaki hareket {expected.value} olmalı "
                f"(seçilen: {payload.type.value})."
            ),
        )

    log = AttendanceLog(
        user_id=staff.id,
        scan_time=occurred_utc,
        type=payload.type,
        source=AttendanceSource.director_manual,
        note=payload.note,
        recorded_by_id=manager.id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    names = await db.execute(select(Campus.name).where(Campus.id == staff.campus_id))
    campus_name = names.scalar_one_or_none()

    return AttendanceLogWithUser(
        id=log.id,
        user_id=log.user_id,
        scan_time=log.scan_time,
        type=log.type,
        status=log.status,
        source=log.source,
        note=log.note,
        user_full_name=staff.full_name,
        campus_name=campus_name,
        recorded_by_name=manager.full_name,
    )


@router.get("/summary/today", response_model=TodaySummary)
async def today_summary(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
):
    """Who is currently inside (last record today is IN), plus daily counts."""
    now_utc = datetime.now(timezone.utc)
    start_utc, end_utc = local_day_bounds_utc(now_utc)
    scope = scope_campus_id(manager, campus_id)

    latest_subq = (
        select(
            AttendanceLog.user_id.label("uid"),
            func.max(AttendanceLog.scan_time).label("max_time"),
        )
        .where(
            AttendanceLog.scan_time >= start_utc,
            AttendanceLog.scan_time <= end_utc,
        )
        .group_by(AttendanceLog.user_id)
        .subquery()
    )

    stmt = (
        select(AttendanceLog, User.full_name, Campus.name)
        .join(
            latest_subq,
            (AttendanceLog.user_id == latest_subq.c.uid)
            & (AttendanceLog.scan_time == latest_subq.c.max_time),
        )
        .join(User, User.id == AttendanceLog.user_id)
        .join(Campus, Campus.id == User.campus_id, isouter=True)
        .order_by(User.full_name)
    )
    if scope is not None:
        stmt = stmt.where(User.campus_id == scope)

    rows = await db.execute(stmt)

    currently_in: list[PresenceEntry] = []
    total_active = 0
    for log, full_name, campus_name in rows.all():
        total_active += 1
        if log.type == AttendanceType.IN:
            currently_in.append(
                PresenceEntry(
                    user_id=log.user_id,
                    full_name=full_name,
                    campus_name=campus_name,
                    since=log.scan_time,
                )
            )

    return TodaySummary(
        date=start_utc.astimezone(ZoneInfo(settings.attendance_timezone)).date(),
        active_today=total_active,
        currently_in_count=len(currently_in),
        currently_in=currently_in,
    )
