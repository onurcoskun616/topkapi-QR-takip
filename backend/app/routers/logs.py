"""Attendance log querying, reporting and CSV export.

Scope:
  * Staff see their own history (``/me``).
  * Campus directors see/export their own campus; head office sees every campus
    (optionally filtered to one with ``campus_id``).
"""
import csv
import io
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_active_staff, get_current_manager
from ..models import AttendanceLog, AttendanceType, Campus, User, UserRole
from ..schemas import (
    AttendanceLogResponse,
    AttendanceLogWithUser,
    PresenceEntry,
    TodaySummary,
)
from ..services import local_day_bounds_utc

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _scope_campus_id(manager: User, requested_campus_id: int | None) -> int | None:
    """Resolve which campus the manager is allowed to query.

    Directors are pinned to their own campus; hq may pass an optional filter.
    """
    if manager.role == UserRole.campus_director:
        return manager.campus_id
    return requested_campus_id  # hq: None == all campuses


def _filtered_logs_stmt(
    campus_id: int | None, user_id: int | None, day: date | None, limit: int | None
) -> Select:
    stmt = (
        select(AttendanceLog, User.full_name, User.phone, Campus.name)
        .join(User, User.id == AttendanceLog.user_id)
        .join(Campus, Campus.id == User.campus_id, isouter=True)
        .order_by(AttendanceLog.scan_time.desc())
    )
    if campus_id is not None:
        stmt = stmt.where(User.campus_id == campus_id)
    if user_id is not None:
        stmt = stmt.where(AttendanceLog.user_id == user_id)
    if day is not None:
        tz = ZoneInfo(settings.attendance_timezone)
        start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
        end = datetime.combine(day, time.max, tzinfo=tz).astimezone(timezone.utc)
        stmt = stmt.where(
            AttendanceLog.scan_time >= start, AttendanceLog.scan_time <= end
        )
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


@router.get("", response_model=list[AttendanceLogWithUser])
async def all_logs(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    user_id: int | None = None,
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    day: date | None = Query(None, description="Filter to a single local day (YYYY-MM-DD)"),
    limit: int = Query(200, ge=1, le=1000),
):
    scope = _scope_campus_id(manager, campus_id)
    result = await db.execute(_filtered_logs_stmt(scope, user_id, day, limit))
    return [
        AttendanceLogWithUser(
            id=log.id,
            user_id=log.user_id,
            scan_time=log.scan_time,
            type=log.type,
            status=log.status,
            user_full_name=full_name,
            campus_name=campus_name,
        )
        for log, full_name, _phone, campus_name in result.all()
    ]


@router.get("/export", response_class=StreamingResponse)
async def export_logs_csv(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    user_id: int | None = None,
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    day: date | None = Query(None, description="Filter to a single local day (YYYY-MM-DD)"),
):
    """Stream filtered attendance logs as a CSV file.

    Timestamps are emitted in both UTC and the configured local timezone so the
    report is unambiguous regardless of who opens it.
    """
    tz = ZoneInfo(settings.attendance_timezone)
    scope = _scope_campus_id(manager, campus_id)
    result = await db.execute(_filtered_logs_stmt(scope, user_id, day, limit=None))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "log_id",
            "user_id",
            "full_name",
            "phone",
            "campus",
            "type",
            "status",
            "scan_time_utc",
            f"scan_time_local ({settings.attendance_timezone})",
        ]
    )
    for log, full_name, phone, campus_name in result.all():
        scan_utc = log.scan_time.astimezone(timezone.utc)
        writer.writerow(
            [
                log.id,
                log.user_id,
                full_name,
                phone or "",
                campus_name or "",
                log.type.value,
                log.status.value,
                scan_utc.isoformat(),
                scan_utc.astimezone(tz).isoformat(),
            ]
        )

    buffer.seek(0)
    filename = f"attendance_{day.isoformat() if day else 'all'}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
    scope = _scope_campus_id(manager, campus_id)

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
