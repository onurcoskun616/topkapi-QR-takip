"""Leave/absence record management.

A campus director (own campus) or hq (any campus) opens a leave record for a
staff member covering a date range: while it is ``active`` and today's local
date falls inside that range, ``/api/scan`` refuses the staff member's scans
and tells them to see their director. If the staff member actually shows up,
the director corrects the record (shorten the range or cancel it) with
``PATCH``/``cancel`` below — scanning then works again immediately, since the
scan-time check simply stops finding an active leave for today.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import date as date_

from ..database import get_db
from ..deps import get_current_manager
from ..models import Campus, LeaveRecord, LeaveStatus, User
from ..schemas import LeaveRecordCreate, LeaveRecordResponse, LeaveRecordUpdate, LeaveTypesResponse
from ..scoping import load_scoped_staff, scope_campus_id
from ..services import SUGGESTED_LEAVE_TYPES

router = APIRouter(prefix="/api/leaves", tags=["leaves"])


async def _to_response(db: AsyncSession, leave: LeaveRecord) -> LeaveRecordResponse:
    staff = await db.get(User, leave.user_id)
    campus_name = None
    if staff and staff.campus_id is not None:
        campus_name = (
            await db.execute(select(Campus.name).where(Campus.id == staff.campus_id))
        ).scalar_one_or_none()
    creator_name = None
    if leave.created_by_id is not None:
        creator = await db.get(User, leave.created_by_id)
        creator_name = creator.full_name if creator else None
    return LeaveRecordResponse(
        id=leave.id,
        user_id=leave.user_id,
        user_full_name=staff.full_name if staff else "—",
        campus_name=campus_name,
        leave_type=leave.leave_type,
        start_date=leave.start_date,
        end_date=leave.end_date,
        note=leave.note,
        status=leave.status,
        created_by_name=creator_name,
        created_at=leave.created_at,
    )


async def _load_scoped_leave(db: AsyncSession, manager: User, leave_id: int) -> LeaveRecord:
    leave = await db.get(LeaveRecord, leave_id)
    if leave is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="İzin kaydı bulunamadı.")
    # Enforces campus scoping by checking the staff member it belongs to.
    await load_scoped_staff(db, manager, leave.user_id)
    return leave


@router.get("/types", response_model=LeaveTypesResponse)
async def leave_types():
    """Suggested (non-exhaustive) reason list for the admin UI dropdown."""
    return LeaveTypesResponse(suggested=SUGGESTED_LEAVE_TYPES)


@router.get("", response_model=list[LeaveRecordResponse])
async def list_leaves(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    user_id: int | None = None,
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
    status_filter: LeaveStatus | None = Query(None, alias="status"),
    start_date: date_ | None = Query(None, description="Only leaves overlapping on/after this date"),
    end_date: date_ | None = Query(None, description="Only leaves overlapping on/before this date"),
):
    scope = scope_campus_id(manager, campus_id)
    stmt = select(LeaveRecord).join(User, User.id == LeaveRecord.user_id)
    if scope is not None:
        stmt = stmt.where(User.campus_id == scope)
    if user_id is not None:
        stmt = stmt.where(LeaveRecord.user_id == user_id)
    if status_filter is not None:
        stmt = stmt.where(LeaveRecord.status == status_filter)
    if end_date is not None:
        stmt = stmt.where(LeaveRecord.start_date <= end_date)
    if start_date is not None:
        stmt = stmt.where(LeaveRecord.end_date >= start_date)
    stmt = stmt.order_by(LeaveRecord.start_date.desc())

    leaves = list((await db.execute(stmt)).scalars().all())
    return [await _to_response(db, leave) for leave in leaves]


@router.post("", response_model=LeaveRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_leave(
    payload: LeaveRecordCreate,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    staff = await load_scoped_staff(db, manager, payload.user_id)
    leave = LeaveRecord(
        user_id=staff.id,
        leave_type=payload.leave_type.strip(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        note=payload.note,
        status=LeaveStatus.active,
        created_by_id=manager.id,
    )
    db.add(leave)
    await db.commit()
    await db.refresh(leave)
    return await _to_response(db, leave)


@router.patch("/{leave_id}", response_model=LeaveRecordResponse)
async def update_leave(
    leave_id: int,
    payload: LeaveRecordUpdate,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Correct a leave record — e.g. shorten the range because the staff
    member showed up and scanned, or cancel it outright."""
    leave = await _load_scoped_leave(db, manager, leave_id)

    if payload.leave_type is not None:
        leave.leave_type = payload.leave_type.strip()
    if payload.start_date is not None:
        leave.start_date = payload.start_date
    if payload.end_date is not None:
        leave.end_date = payload.end_date
    if payload.note is not None:
        leave.note = payload.note
    if payload.status is not None:
        leave.status = payload.status

    if leave.end_date < leave.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="end_date, start_date'den önce olamaz."
        )

    await db.commit()
    await db.refresh(leave)
    return await _to_response(db, leave)


@router.post("/{leave_id}/cancel", response_model=LeaveRecordResponse)
async def cancel_leave(
    leave_id: int,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Withdraw a leave record entirely — the staff member regains the
    ability to scan normally for the whole period."""
    leave = await _load_scoped_leave(db, manager, leave_id)
    leave.status = LeaveStatus.cancelled
    await db.commit()
    await db.refresh(leave)
    return await _to_response(db, leave)
