"""Campus listing — public so the PWA registration form can show the dropdown."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Campus
from ..schemas import CampusResponse

router = APIRouter(prefix="/api/campuses", tags=["campuses"])


@router.get("", response_model=list[CampusResponse])
async def list_campuses(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Campus).order_by(Campus.name))
    return list(result.scalars().all())
