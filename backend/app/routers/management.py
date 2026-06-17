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
from ..schemas import (
    DirectorCreate,
    DirectorPasswordUpdate,
    StaffBulkCreate,
    StaffBulkResult,
    StaffBulkRowResult,
    StaffUpdate,
    UserResponse,
)
from ..scoping import load_scoped_staff
from ..security import hash_password
from ..serializers import to_user_response
from ..services import format_working_days, normalize_phone

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


@router.post("/staff/bulk", response_model=StaffBulkResult, status_code=status.HTTP_201_CREATED)
async def bulk_create_staff(
    payload: StaffBulkCreate,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Import many staff at once (e.g. a start-of-year roster).

    Each row becomes an **active** account with no bound device; the staff
    member binds a phone later by self-registering from the PWA with the same
    phone number (the re-claim path keeps the imported profile and approval).

    Scope: a director's rows all land on their own campus; hq targets the
    per-row ``campus_id`` (falling back to the request-level ``campus_id``).
    Rows whose phone is already registered are skipped and reported, so the
    same file can be re-uploaded safely (idempotent on phone number).
    """
    valid_campus_ids = {
        cid for (cid,) in (await db.execute(select(Campus.id))).all()
    }
    # Phones already taken — checked up front so a duplicate inside the same
    # upload is also caught (not just collisions with existing accounts).
    seen_phones: set[str] = set()
    results: list[StaffBulkRowResult] = []
    created_count = 0

    for row in payload.rows:
        phone = normalize_phone(row.phone)
        if len(phone) < 7:
            results.append(StaffBulkRowResult(
                full_name=row.full_name, phone=row.phone, created=False,
                reason="Geçersiz telefon numarası.",
            ))
            continue

        if manager.role == UserRole.campus_director:
            campus_id = manager.campus_id
        else:
            campus_id = row.campus_id or payload.campus_id
        if campus_id is None:
            results.append(StaffBulkRowResult(
                full_name=row.full_name, phone=phone, created=False,
                reason="Kampüs belirtilmedi.",
            ))
            continue
        if campus_id not in valid_campus_ids:
            results.append(StaffBulkRowResult(
                full_name=row.full_name, phone=phone, created=False,
                reason="Geçersiz kampüs.",
            ))
            continue

        if phone in seen_phones:
            results.append(StaffBulkRowResult(
                full_name=row.full_name, phone=phone, created=False,
                reason="Bu telefon dosyada birden fazla kez var.",
            ))
            continue
        existing = (
            await db.execute(select(User.id).where(User.phone == phone))
        ).first()
        if existing:
            results.append(StaffBulkRowResult(
                full_name=row.full_name, phone=phone, created=False,
                reason="Bu telefon zaten kayıtlı.",
            ))
            continue

        db.add(User(
            full_name=row.full_name.strip(),
            phone=phone,
            job_title=row.job_title.strip(),
            branch=row.branch.strip(),
            birth_date=row.birth_date,
            role=UserRole.staff,
            status=UserStatus.active,
            campus_id=campus_id,
        ))
        seen_phones.add(phone)
        created_count += 1
        results.append(StaffBulkRowResult(
            full_name=row.full_name.strip(), phone=phone, created=True,
        ))

    if created_count:
        await db.commit()

    return StaffBulkResult(
        created_count=created_count,
        skipped_count=len(results) - created_count,
        results=results,
    )


@router.post("/staff/{staff_id}/approve", response_model=UserResponse)
async def approve_staff(
    staff_id: int,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending registration so the staff member may start scanning."""
    staff = await load_scoped_staff(db, manager, staff_id)
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
    staff = await load_scoped_staff(db, manager, staff_id)
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
    staff = await load_scoped_staff(db, manager, staff_id)
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
    staff = await load_scoped_staff(db, manager, staff_id)

    if payload.full_name is not None:
        staff.full_name = payload.full_name.strip()
    if payload.job_title is not None:
        staff.job_title = payload.job_title.strip()
    if payload.branch is not None:
        staff.branch = payload.branch.strip()
    if payload.birth_date is not None:
        staff.birth_date = payload.birth_date
    # working_days is presence-detected so "" / null / [] can clear it back to
    # the default Mon–Fri week, while omitting it leaves the schedule untouched.
    if "working_days" in payload.model_fields_set:
        staff.working_days = format_working_days(payload.working_days)
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


@router.post(
    "/directors/{director_id}/enable",
    response_model=UserResponse,
    dependencies=[Depends(get_current_hq)],
)
async def enable_director(director_id: int, db: AsyncSession = Depends(get_db)):
    """Re-activate a previously disabled director account."""
    director = await db.get(User, director_id)
    if director is None or director.role != UserRole.campus_director:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Müdür bulunamadı.")
    director.status = UserStatus.active
    await db.commit()
    names = await _campus_names(db)
    return to_user_response(director, campus_name=names.get(director.campus_id))


@router.post(
    "/directors/{director_id}/password",
    response_model=UserResponse,
    dependencies=[Depends(get_current_hq)],
)
async def update_director_password(
    director_id: int,
    payload: DirectorPasswordUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Reset a director's password and drop their sessions (re-login required)."""
    director = await db.get(User, director_id)
    if director is None or director.role != UserRole.campus_director:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Müdür bulunamadı.")
    director.password_hash = hash_password(payload.password)
    await db.execute(delete(Session).where(Session.user_id == director.id))
    await db.commit()
    names = await _campus_names(db)
    return to_user_response(director, campus_name=names.get(director.campus_id))
