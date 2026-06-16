"""Campus listing — public so the PWA registration form can show the dropdown.

Work-hours / shift schedule (``shift_start``/``shift_end``) may only be set by
head office (hq); campus directors have no write access to it (enforced by
``get_current_hq`` below).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_hq
from ..models import Campus
from ..schemas import CampusResponse, CampusShiftUpdate

router = APIRouter(prefix="/api/campuses", tags=["campuses"])


@router.get("", response_model=list[CampusResponse])
async def list_campuses(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campus).order_by(Campus.name))
    return list(result.scalars().all())


@router.patch(
    "/{campus_id}/shift",
    response_model=CampusResponse,
    dependencies=[Depends(get_current_hq)],
)
async def update_campus_shift(
    campus_id: int, payload: CampusShiftUpdate, db: AsyncSession = Depends(get_db)
):
    campus = await db.get(Campus, campus_id)
    if campus is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kampüs bulunamadı.")
    campus.shift_start = payload.shift_start
    campus.shift_end = payload.shift_end
    await db.commit()
    await db.refresh(campus)
    return campus
