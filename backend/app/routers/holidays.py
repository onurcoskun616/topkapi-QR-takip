"""Official holiday / campus-closure management.

A holiday excludes its date from absence counting: on a covered day the reports
expect nobody to be present, so it is neither an absence nor ``unresolved``.

Scope:
  * **campus_director** — manages holidays for *their own* campus, and sees the
    national (all-campus) holidays that apply to them (read-only).
  * **hq** — manages every holiday, national (``campus_id`` = null) or scoped to
    a single campus.
"""
from datetime import date as date_

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_manager
from ..models import Campus, Holiday, User, UserRole
from ..schemas import HolidayCreate, HolidayResponse

router = APIRouter(prefix="/api/holidays", tags=["holidays"])


async def _campus_names(db: AsyncSession) -> dict[int, str]:
    rows = await db.execute(select(Campus.id, Campus.name))
    return {cid: name for cid, name in rows.all()}


def _to_response(holiday: Holiday, names: dict[int, str]) -> HolidayResponse:
    return HolidayResponse(
        id=holiday.id,
        date=holiday.date,
        name=holiday.name,
        campus_id=holiday.campus_id,
        campus_name=names.get(holiday.campus_id) if holiday.campus_id else None,
        created_at=holiday.created_at,
    )


@router.get("", response_model=list[HolidayResponse])
async def list_holidays(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    start_date: date_ | None = Query(None),
    end_date: date_ | None = Query(None),
):
    stmt = select(Holiday)
    if manager.role == UserRole.campus_director:
        # Own campus closures + national (all-campus) holidays that apply to them.
        stmt = stmt.where(
            or_(Holiday.campus_id == manager.campus_id, Holiday.campus_id.is_(None))
        )
    elif campus_id is not None:
        stmt = stmt.where(
            or_(Holiday.campus_id == campus_id, Holiday.campus_id.is_(None))
        )
    if start_date is not None:
        stmt = stmt.where(Holiday.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Holiday.date <= end_date)
    stmt = stmt.order_by(Holiday.date.desc())

    holidays = list((await db.execute(stmt)).scalars().all())
    names = await _campus_names(db)
    return [_to_response(h, names) for h in holidays]


@router.post("", response_model=HolidayResponse, status_code=status.HTTP_201_CREATED)
async def create_holiday(
    payload: HolidayCreate,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    # A director can only create closures for their own campus; hq may create a
    # national holiday (campus_id null) or scope it to any campus.
    if manager.role == UserRole.campus_director:
        campus_id = manager.campus_id
    else:
        campus_id = payload.campus_id
        if campus_id is not None and await db.get(Campus, campus_id) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz kampüs.")

    # Avoid duplicates for the same scope/date.
    existing = await db.execute(
        select(Holiday.id).where(
            Holiday.date == payload.date,
            Holiday.campus_id.is_(None) if campus_id is None else Holiday.campus_id == campus_id,
        )
    )
    if existing.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu tarih için zaten bir tatil kaydı var.",
        )

    holiday = Holiday(
        date=payload.date,
        name=payload.name.strip(),
        campus_id=campus_id,
        created_by_id=manager.id,
    )
    db.add(holiday)
    await db.commit()
    await db.refresh(holiday)
    names = await _campus_names(db)
    return _to_response(holiday, names)


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(
    holiday_id: int,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    holiday = await db.get(Holiday, holiday_id)
    if holiday is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tatil kaydı bulunamadı.")
    # A director may only remove their own campus' closures, never a national one.
    if manager.role == UserRole.campus_director and holiday.campus_id != manager.campus_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu tatil kaydını yalnızca genel merkez kaldırabilir.",
        )
    await db.delete(holiday)
    await db.commit()
