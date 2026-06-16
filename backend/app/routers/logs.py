"""Attendance log querying.

* Teachers can list their own history.
* Admins can list everyone's, optionally filtered by user/date.
"""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_admin, get_current_user
from ..models import AttendanceLog, User
from ..schemas import AttendanceLogResponse, AttendanceLogWithUser

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/me", response_model=list[AttendanceLogResponse])
async def my_logs(
    current: User = Depends(get_current_user),
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


@router.get(
    "",
    response_model=list[AttendanceLogWithUser],
    dependencies=[Depends(get_current_admin)],
)
async def all_logs(
    db: AsyncSession = Depends(get_db),
    user_id: int | None = None,
    day: date | None = Query(None, description="Filter to a single local day (YYYY-MM-DD)"),
    limit: int = Query(200, ge=1, le=1000),
):
    stmt = (
        select(AttendanceLog, User.full_name)
        .join(User, User.id == AttendanceLog.user_id)
        .order_by(AttendanceLog.scan_time.desc())
        .limit(limit)
    )
    if user_id is not None:
        stmt = stmt.where(AttendanceLog.user_id == user_id)
    if day is not None:
        tz = ZoneInfo(settings.attendance_timezone)
        start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
        end = datetime.combine(day, time.max, tzinfo=tz).astimezone(timezone.utc)
        stmt = stmt.where(
            AttendanceLog.scan_time >= start, AttendanceLog.scan_time <= end
        )

    result = await db.execute(stmt)
    return [
        AttendanceLogWithUser(
            id=log.id,
            user_id=log.user_id,
            scan_time=log.scan_time,
            type=log.type,
            status=log.status,
            user_full_name=full_name,
        )
        for log, full_name in result.all()
    ]
