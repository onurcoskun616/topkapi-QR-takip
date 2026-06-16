"""Management endpoints.

Scope rules:
  * **campus_director** — may see and act on the staff of *their own* campus only.
  * **hq** — may see and act on every campus, and additionally create/list/disable
    campus directors.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_hq, get_current_manager
from ..models import Campus, Session, User, UserRole, UserStatus
from ..schemas import DirectorCreate, StaffUpdate, UserResponse
from ..security import hash_password
from ..serializers import to_user_response

router = APIRouter(prefix="/api", tags=["management"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _campus_names(db: AsyncSession) -> dict[int, str]:
    rows = await db.execute(select(Campus.id, Campus.name))
    return {cid: name for cid, name in rows.all()}


async def _users_with_device(db: AsyncSession, user_ids: list[int]) -> set[int]:
    """Subset of the given users that currently have a live device session."""
    if not user_ids:
        return set()
    now = datetime.now(timezone.utc)
    rows = await db.execute(
        select(Session.user_id)
        .where(
            Session.user_id.in_(user_ids),
            Session.revoked.is_(False),
            Session.expires_at > now,
        )
        .distinct()
    )
    return {uid for (uid,) in rows.all()}


async def _load_scoped_staff(db: AsyncSession, manager: User, staff_id: int) -> User:
    """Fetch a staff user, enforcing that the manager is allowed to touch it."""
    staff = await db.get(User, staff_id)
    if staff is None or staff.role != UserRole.staff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personel bulunamadı.")
    if manager.role == UserRole.campus_director and staff.campus_id != manager.campus_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu personel sizin kampüsünüze ait değil.",
        )
    return staff


# --------------------------------------------------------------------------- #
# Staff (director scope = own campus, hq = all)
# --------------------------------------------------------------------------- #
@router.get("/staff", response_model=list[UserResponse])
async def list_staff(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    status_filter: UserStatus | None = Query(None, alias="status"),
    campus_id: int | None = None,
):
    stmt = select(User).where(User.role == UserRole.staff).order_by(User.full_name)

    if manager.role == UserRole.campus_director:
        stmt = stmt.where(User.campus_id == manager.campus_id)
    elif campus_id is not None:  # hq optional filter
        stmt = stmt.where(User.campus_id == campus_id)

    if status_filter is not None:
        stmt = stmt.where(User.status == status_filter)

    staff = list((await db.execute(stmt)).scalars().all())
    names = await _campus_names(db)
    with_device = await _users_with_device(db, [s.id for s in staff])
    return [
        to_user_response(
            s, campus_name=names.get(s.campus_id), has_device=s.id in with_device
        )
        for s in staff
    ]


@router.post("/staff/{staff_id}/approve", response_model=UserResponse)
async def approve_staff(
    staff_id: int,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending registration so the staff member may start scanning."""
    staff = await _load_scoped_staff(db, manager, staff_id)
    if staff.status == UserStatus.disabled:
        staff.status = UserStatus.active
    elif staff.status == UserStatus.pending:
        staff.status = UserStatus.active
    await db.commit()
    names = await _campus_names(db)
    has_device = staff.id in await _users_with_device(db, [staff.id])
    return to_user_response(staff, campus_name=names.get(staff.campus_id), has_device=has_device)


@router.post("/staff/{staff_id}/disable", response_model=UserResponse)
async def disable_staff(
    staff_id: int,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate an account and drop its device session (full lock-out)."""
    staff = await _load_scoped_staff(db, manager, staff_id)
    staff.status = UserStatus.disabled
    await db.execute(delete(Session).where(Session.user_id == staff.id))
    await db.commit()
    names = await _campus_names(db)
    return to_user_response(staff, campus_name=names.get(staff.campus_id), has_device=False)


@router.post("/staff/{staff_id}/reset-device", response_model=UserResponse)
async def reset_device(
    staff_id: int,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Clear the bound device so the staff member can register a new phone.

    The identity (phone number, history, approval) is preserved; only the device
    binding is removed. The staff member then re-opens the PWA on the new phone
    and re-registers with the *same* phone number to bind it.
    """
    staff = await _load_scoped_staff(db, manager, staff_id)
    await db.execute(delete(Session).where(Session.user_id == staff.id))
    await db.commit()
    names = await _campus_names(db)
    return to_user_response(staff, campus_name=names.get(staff.campus_id), has_device=False)


@router.patch("/staff/{staff_id}", response_model=UserResponse)
async def update_staff(
    staff_id: int,
    payload: StaffUpdate,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Correct a staff profile (name / görev / branş / campus)."""
    staff = await _load_scoped_staff(db, manager, staff_id)

    if payload.full_name is not None:
        staff.full_name = payload.full_name.strip()
    if payload.job_title is not None:
        staff.job_title = payload.job_title.strip()
    if payload.branch is not None:
        staff.branch = payload.branch.strip()
    if payload.campus_id is not None and payload.campus_id != staff.campus_id:
        # A director may not move staff out of their own campus.
        if manager.role == UserRole.campus_director:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kampüs değişikliğini yalnızca genel merkez yapabilir.",
            )
        target = await db.get(Campus, payload.campus_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz kampüs.")
        staff.campus_id = payload.campus_id

    await db.commit()
    names = await _campus_names(db)
    has_device = staff.id in await _users_with_device(db, [staff.id])
    return to_user_response(staff, campus_name=names.get(staff.campus_id), has_device=has_device)


# --------------------------------------------------------------------------- #
# Directors (hq only)
# --------------------------------------------------------------------------- #
@router.get("/directors", response_model=list[UserResponse], dependencies=[Depends(get_current_hq)])
async def list_directors(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(User).where(User.role == UserRole.campus_director).order_by(User.full_name)
    )
    directors = list(rows.scalars().all())
    names = await _campus_names(db)
    return [to_user_response(d, campus_name=names.get(d.campus_id)) for d in directors]


@router.post(
    "/directors",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_hq)],
)
async def create_director(payload: DirectorCreate, db: AsyncSession = Depends(get_db)):
    campus = await db.get(Campus, payload.campus_id)
    if campus is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz kampüs.")

    email = payload.email.lower()
    if (await db.execute(select(User.id).where(User.email == email))).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu e-posta zaten kayıtlı.")

    director = User(
        full_name=payload.full_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role=UserRole.campus_director,
        status=UserStatus.active,
        campus_id=campus.id,
    )
    db.add(director)
    await db.commit()
    await db.refresh(director)
    return to_user_response(director, campus_name=campus.name)


@router.post(
    "/directors/{director_id}/disable",
    response_model=UserResponse,
    dependencies=[Depends(get_current_hq)],
)
async def disable_director(director_id: int, db: AsyncSession = Depends(get_db)):
    director = await db.get(User, director_id)
    if director is None or director.role != UserRole.campus_director:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Müdür bulunamadı.")
    director.status = UserStatus.disabled
    await db.execute(delete(Session).where(Session.user_id == director.id))
    await db.commit()
    names = await _campus_names(db)
    return to_user_response(director, campus_name=names.get(director.campus_id))
