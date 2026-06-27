"""Student registration tracking: campus departments, MEB license quotas,
per-grade internal/external targets, and the student registration records that
fill them.

Scope rules
-----------
* **Departments + quotas + targets** are managed *centrally* (head office /
  merkez): only ``hq`` may create/update/delete them. A campus director may
  read their own campus' departments.
* **Student registrations** are managed per campus: a campus director acts on
  *their own* campus only; ``hq`` acts on/filters across all campuses.

Counting rule
-------------
A registration counts toward its department's license quota and toward the
internal/external target of its (department, grade) **only when** it is both
``registered`` (status) and ``approved`` (by a campus manager — müdür / müdür
yardımcısı). Its kind is internal when the arrival channel is ``İç Kayıt`` and
external for every other channel.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_hq, get_current_manager
from ..models import (
    Campus,
    Department,
    REGISTRATION_GRADES,
    RegistrationStatus,
    RegistrationTarget,
    StudentRegistration,
    User,
    UserRole,
)
from ..schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentTargetsUpdate,
    DepartmentUpdate,
    RegistrationDepartmentSummary,
    RegistrationGradeSummary,
    RegistrationSummaryResponse,
    RegistrationTargetItem,
    StudentRegistrationCreate,
    StudentRegistrationResponse,
    StudentRegistrationUpdate,
)
from ..scoping import scope_campus_id
from ..services import is_internal_channel

router = APIRouter(prefix="/api", tags=["registrations"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _campus_names(db: AsyncSession) -> dict[int, str]:
    rows = await db.execute(select(Campus.id, Campus.name))
    return {cid: name for cid, name in rows.all()}


def _targets_of(department: Department) -> list[RegistrationTargetItem]:
    by_grade = {t.grade: t for t in department.targets}
    return [
        RegistrationTargetItem(
            grade=g,
            internal_target=by_grade[g].internal_target if g in by_grade else 0,
            external_target=by_grade[g].external_target if g in by_grade else 0,
        )
        for g in REGISTRATION_GRADES
    ]


async def _confirmed_count(
    db: AsyncSession, department_id: int, *, exclude_id: int | None = None
) -> int:
    """Number of confirmed (registered + approved) registrations in a department.

    This is what the MEB license quota caps. ``exclude_id`` leaves the record
    being created/updated out of the tally so a re-save of an already-counted
    row doesn't double-count against its own quota.
    """
    stmt = select(func.count(StudentRegistration.id)).where(
        StudentRegistration.department_id == department_id,
        StudentRegistration.status == RegistrationStatus.registered,
        StudentRegistration.approved.is_(True),
    )
    if exclude_id is not None:
        stmt = stmt.where(StudentRegistration.id != exclude_id)
    return int((await db.execute(stmt)).scalar_one())


async def _ensure_within_quota(
    db: AsyncSession,
    department: Department,
    *,
    new_status: RegistrationStatus,
    new_approved: bool,
    exclude_id: int | None = None,
) -> None:
    """Raise 409 if making a registration confirmed would exceed the license
    quota. A no-op for any state that doesn't count (not registered / not
    approved)."""
    if not (new_status == RegistrationStatus.registered and new_approved):
        return
    used = await _confirmed_count(db, department.id, exclude_id=exclude_id)
    if used + 1 > department.license_quota:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{department.name} bölümünün ruhsat kontenjanı dolu "
                f"({used}/{department.license_quota}). Daha fazla kayıt onaylanamaz."
            ),
        )


def _to_department_response(
    department: Department, *, campus_name: str | None, confirmed_count: int
) -> DepartmentResponse:
    return DepartmentResponse(
        id=department.id,
        campus_id=department.campus_id,
        campus_name=campus_name,
        name=department.name,
        license_quota=department.license_quota,
        targets=_targets_of(department),
        confirmed_count=confirmed_count,
        remaining_quota=max(0, department.license_quota - confirmed_count),
        created_at=department.created_at,
    )


def _to_registration_response(
    reg: StudentRegistration,
    *,
    campus_name: str | None,
    department_name: str | None,
    approved_by_name: str | None,
) -> StudentRegistrationResponse:
    internal = is_internal_channel(reg.arrival_channel)
    counts = reg.status == RegistrationStatus.registered and reg.approved
    return StudentRegistrationResponse(
        id=reg.id,
        campus_id=reg.campus_id,
        campus_name=campus_name,
        department_id=reg.department_id,
        department_name=department_name,
        full_name=reg.full_name,
        grade=reg.grade,
        section=reg.section,
        arrival_channel=reg.arrival_channel,
        is_internal=internal,
        status=reg.status,
        approved=reg.approved,
        counts_toward_target=counts,
        approved_by_name=approved_by_name,
        approved_at=reg.approved_at,
        created_at=reg.created_at,
    )


async def _load_scoped_registration(
    db: AsyncSession, manager: User, registration_id: int
) -> StudentRegistration:
    reg = await db.get(StudentRegistration, registration_id)
    if reg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kayıt bulunamadı.")
    if manager.role == UserRole.campus_director and reg.campus_id != manager.campus_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu kayıt sizin kampüsünüze ait değil.",
        )
    return reg


async def _serialize_registration(
    db: AsyncSession, reg: StudentRegistration
) -> StudentRegistrationResponse:
    names = await _campus_names(db)
    department = await db.get(Department, reg.department_id)
    approver_name = None
    if reg.approved_by_id is not None:
        approver = await db.get(User, reg.approved_by_id)
        approver_name = approver.full_name if approver else None
    return _to_registration_response(
        reg,
        campus_name=names.get(reg.campus_id),
        department_name=department.name if department else None,
        approved_by_name=approver_name,
    )


# --------------------------------------------------------------------------- #
# Departments (read: managers in scope; write: hq only)
# --------------------------------------------------------------------------- #
@router.get("/departments", response_model=list[DepartmentResponse])
async def list_departments(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = None,
):
    target_campus = scope_campus_id(manager, campus_id)
    stmt = select(Department).order_by(Department.campus_id, Department.name)
    if target_campus is not None:
        stmt = stmt.where(Department.campus_id == target_campus)
    departments = list((await db.execute(stmt)).scalars().all())
    for d in departments:  # eager-load targets for serialisation
        await db.refresh(d, attribute_names=["targets"])

    names = await _campus_names(db)
    out: list[DepartmentResponse] = []
    for d in departments:
        confirmed = await _confirmed_count(db, d.id)
        out.append(_to_department_response(d, campus_name=names.get(d.campus_id), confirmed_count=confirmed))
    return out


@router.post(
    "/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_hq)],
)
async def create_department(payload: DepartmentCreate, db: AsyncSession = Depends(get_db)):
    campus = await db.get(Campus, payload.campus_id)
    if campus is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz kampüs.")
    name = payload.name.strip()
    dup = (
        await db.execute(
            select(Department.id).where(
                Department.campus_id == payload.campus_id, Department.name == name
            )
        )
    ).first()
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kampüste aynı isimde bir bölüm zaten var.",
        )
    department = Department(
        campus_id=payload.campus_id, name=name, license_quota=payload.license_quota
    )
    db.add(department)
    await db.commit()
    await db.refresh(department, attribute_names=["targets"])
    return _to_department_response(department, campus_name=campus.name, confirmed_count=0)


@router.patch(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    dependencies=[Depends(get_current_hq)],
)
async def update_department(
    department_id: int, payload: DepartmentUpdate, db: AsyncSession = Depends(get_db)
):
    department = await db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bölüm bulunamadı.")
    if payload.name is not None:
        name = payload.name.strip()
        dup = (
            await db.execute(
                select(Department.id).where(
                    Department.campus_id == department.campus_id,
                    Department.name == name,
                    Department.id != department.id,
                )
            )
        ).first()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu kampüste aynı isimde bir bölüm zaten var.",
            )
        department.name = name
    if payload.license_quota is not None:
        department.license_quota = payload.license_quota
    await db.commit()
    await db.refresh(department, attribute_names=["targets"])
    names = await _campus_names(db)
    confirmed = await _confirmed_count(db, department.id)
    return _to_department_response(
        department, campus_name=names.get(department.campus_id), confirmed_count=confirmed
    )


@router.put(
    "/departments/{department_id}/targets",
    response_model=DepartmentResponse,
    dependencies=[Depends(get_current_hq)],
)
async def set_department_targets(
    department_id: int, payload: DepartmentTargetsUpdate, db: AsyncSession = Depends(get_db)
):
    """Replace the per-grade internal/external targets for a department.

    Grades not present in the payload are reset to 0/0.
    """
    department = await db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bölüm bulunamadı.")
    await db.refresh(department, attribute_names=["targets"])

    wanted = {t.grade: t for t in payload.targets}
    existing = {t.grade: t for t in department.targets}
    for grade in REGISTRATION_GRADES:
        item = wanted.get(grade)
        row = existing.get(grade)
        if item is None:
            if row is not None:  # cleared → drop the row
                await db.delete(row)
            continue
        if row is None:
            db.add(
                RegistrationTarget(
                    department_id=department.id,
                    grade=grade,
                    internal_target=item.internal_target,
                    external_target=item.external_target,
                )
            )
        else:
            row.internal_target = item.internal_target
            row.external_target = item.external_target
    await db.commit()
    await db.refresh(department, attribute_names=["targets"])
    names = await _campus_names(db)
    confirmed = await _confirmed_count(db, department.id)
    return _to_department_response(
        department, campus_name=names.get(department.campus_id), confirmed_count=confirmed
    )


@router.delete(
    "/departments/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_hq)],
)
async def delete_department(department_id: int, db: AsyncSession = Depends(get_db)):
    department = await db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bölüm bulunamadı.")
    has_students = (
        await db.execute(
            select(StudentRegistration.id)
            .where(StudentRegistration.department_id == department_id)
            .limit(1)
        )
    ).first()
    if has_students:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu bölümde öğrenci kayıtları var; önce kayıtları taşıyın/silin.",
        )
    await db.delete(department)
    await db.commit()
    return None


# --------------------------------------------------------------------------- #
# Student registrations (director: own campus, hq: all/filter)
# --------------------------------------------------------------------------- #
@router.get("/registrations", response_model=list[StudentRegistrationResponse])
async def list_registrations(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = None,
    department_id: int | None = None,
    grade: int | None = Query(None, ge=9, le=12),
    section: str | None = None,
    status_filter: RegistrationStatus | None = Query(None, alias="status"),
    approved: bool | None = None,
    channel: str | None = None,
    q: str | None = None,
):
    """Search form (arama formu) over student registrations, scoped to campus."""
    stmt = select(StudentRegistration).order_by(
        StudentRegistration.full_name
    )
    target_campus = scope_campus_id(manager, campus_id)
    if target_campus is not None:
        stmt = stmt.where(StudentRegistration.campus_id == target_campus)
    if department_id is not None:
        stmt = stmt.where(StudentRegistration.department_id == department_id)
    if grade is not None:
        stmt = stmt.where(StudentRegistration.grade == grade)
    if section:
        stmt = stmt.where(StudentRegistration.section == section)
    if status_filter is not None:
        stmt = stmt.where(StudentRegistration.status == status_filter)
    if approved is not None:
        stmt = stmt.where(StudentRegistration.approved.is_(approved))
    if channel:
        stmt = stmt.where(StudentRegistration.arrival_channel == channel)
    if q:
        stmt = stmt.where(StudentRegistration.full_name.ilike(f"%{q.strip()}%"))

    regs = list((await db.execute(stmt)).scalars().all())
    names = await _campus_names(db)
    dept_rows = await db.execute(select(Department.id, Department.name))
    dept_names = {did: dname for did, dname in dept_rows.all()}
    approver_ids = {r.approved_by_id for r in regs if r.approved_by_id is not None}
    approver_names: dict[int, str] = {}
    if approver_ids:
        rows = await db.execute(
            select(User.id, User.full_name).where(User.id.in_(approver_ids))
        )
        approver_names = {uid: uname for uid, uname in rows.all()}

    return [
        _to_registration_response(
            r,
            campus_name=names.get(r.campus_id),
            department_name=dept_names.get(r.department_id),
            approved_by_name=approver_names.get(r.approved_by_id),
        )
        for r in regs
    ]


@router.post(
    "/registrations",
    response_model=StudentRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_registration(
    payload: StudentRegistrationCreate,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    department = await db.get(Department, payload.department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz bölüm.")
    if (
        manager.role == UserRole.campus_director
        and department.campus_id != manager.campus_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu bölüm sizin kampüsünüze ait değil.",
        )

    await _ensure_within_quota(
        db, department, new_status=payload.status, new_approved=payload.approved
    )

    now = datetime.now(timezone.utc)
    reg = StudentRegistration(
        campus_id=department.campus_id,
        department_id=department.id,
        full_name=payload.full_name.strip(),
        grade=payload.grade,
        section=(payload.section or "").strip() or None,
        arrival_channel=payload.arrival_channel.strip(),
        status=payload.status,
        approved=payload.approved,
        approved_by_id=manager.id if payload.approved else None,
        approved_at=now if payload.approved else None,
        created_by_id=manager.id,
    )
    db.add(reg)
    await db.commit()
    await db.refresh(reg)
    return await _serialize_registration(db, reg)


@router.patch("/registrations/{registration_id}", response_model=StudentRegistrationResponse)
async def update_registration(
    registration_id: int,
    payload: StudentRegistrationUpdate,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    reg = await _load_scoped_registration(db, manager, registration_id)

    # Resolve the target department (may be moving the student to another one).
    department = await db.get(Department, payload.department_id or reg.department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz bölüm.")
    if (
        manager.role == UserRole.campus_director
        and department.campus_id != manager.campus_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu bölüm sizin kampüsünüze ait değil.",
        )

    new_status = payload.status if payload.status is not None else reg.status
    new_channel = (
        payload.arrival_channel.strip()
        if payload.arrival_channel is not None
        else reg.arrival_channel
    )
    # Quota check against the resulting confirmed state in the target department.
    await _ensure_within_quota(
        db, department, new_status=new_status, new_approved=reg.approved, exclude_id=reg.id
    )

    reg.department_id = department.id
    reg.campus_id = department.campus_id
    if payload.full_name is not None:
        reg.full_name = payload.full_name.strip()
    if payload.grade is not None:
        reg.grade = payload.grade
    if payload.section is not None:
        reg.section = payload.section.strip() or None
    reg.arrival_channel = new_channel
    reg.status = new_status

    await db.commit()
    await db.refresh(reg)
    return await _serialize_registration(db, reg)


@router.post("/registrations/{registration_id}/approve", response_model=StudentRegistrationResponse)
async def approve_registration(
    registration_id: int,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Müdür / müdür yardımcısı onayı. Once approved *and* the status is
    ``registered``, the student is credited to the department quota and to the
    internal/external target of its (department, grade)."""
    reg = await _load_scoped_registration(db, manager, registration_id)
    department = await db.get(Department, reg.department_id)
    await _ensure_within_quota(
        db, department, new_status=reg.status, new_approved=True, exclude_id=reg.id
    )
    reg.approved = True
    reg.approved_by_id = manager.id
    reg.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(reg)
    return await _serialize_registration(db, reg)


@router.post("/registrations/{registration_id}/unapprove", response_model=StudentRegistrationResponse)
async def unapprove_registration(
    registration_id: int,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """Withdraw approval (e.g. the registration was approved by mistake). Frees
    the license slot and removes the student from the credited targets."""
    reg = await _load_scoped_registration(db, manager, registration_id)
    reg.approved = False
    reg.approved_by_id = None
    reg.approved_at = None
    await db.commit()
    await db.refresh(reg)
    return await _serialize_registration(db, reg)


@router.delete("/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_registration(
    registration_id: int,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    reg = await _load_scoped_registration(db, manager, registration_id)
    await db.execute(
        delete(StudentRegistration).where(StudentRegistration.id == reg.id)
    )
    await db.commit()
    return None


# --------------------------------------------------------------------------- #
# Summary dashboard — quota usage + target fill per department/grade
# --------------------------------------------------------------------------- #
@router.get("/registrations/summary", response_model=RegistrationSummaryResponse)
async def registration_summary(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = None,
):
    """Per-department, per-grade dashboard: license quota usage and how full the
    internal/external targets are (counting only registered + approved students)."""
    target_campus = scope_campus_id(manager, campus_id)

    dept_stmt = select(Department).order_by(Department.campus_id, Department.name)
    if target_campus is not None:
        dept_stmt = dept_stmt.where(Department.campus_id == target_campus)
    departments = list((await db.execute(dept_stmt)).scalars().all())
    for d in departments:
        await db.refresh(d, attribute_names=["targets"])

    names = await _campus_names(db)

    # Confirmed registrations grouped by (department, grade, arrival_channel).
    counts_stmt = select(
        StudentRegistration.department_id,
        StudentRegistration.grade,
        StudentRegistration.arrival_channel,
        func.count(StudentRegistration.id),
    ).where(
        StudentRegistration.status == RegistrationStatus.registered,
        StudentRegistration.approved.is_(True),
    )
    if target_campus is not None:
        counts_stmt = counts_stmt.where(StudentRegistration.campus_id == target_campus)
    counts_stmt = counts_stmt.group_by(
        StudentRegistration.department_id,
        StudentRegistration.grade,
        StudentRegistration.arrival_channel,
    )
    # (department_id, grade) -> [internal_count, external_count]
    grade_counts: dict[tuple[int, int], list[int]] = {}
    for dept_id, grade, channel, n in (await db.execute(counts_stmt)).all():
        key = (dept_id, grade)
        bucket = grade_counts.setdefault(key, [0, 0])
        if is_internal_channel(channel):
            bucket[0] += int(n)
        else:
            bucket[1] += int(n)

    out: list[RegistrationDepartmentSummary] = []
    for d in departments:
        by_grade = {t.grade: t for t in d.targets}
        grade_rows: list[RegistrationGradeSummary] = []
        confirmed_total = 0
        for g in REGISTRATION_GRADES:
            internal_count, external_count = grade_counts.get((d.id, g), [0, 0])
            confirmed_total += internal_count + external_count
            target = by_grade.get(g)
            grade_rows.append(
                RegistrationGradeSummary(
                    grade=g,
                    internal_target=target.internal_target if target else 0,
                    external_target=target.external_target if target else 0,
                    internal_count=internal_count,
                    external_count=external_count,
                )
            )
        out.append(
            RegistrationDepartmentSummary(
                department_id=d.id,
                department_name=d.name,
                campus_id=d.campus_id,
                campus_name=names.get(d.campus_id),
                license_quota=d.license_quota,
                confirmed_count=confirmed_total,
                remaining_quota=max(0, d.license_quota - confirmed_total),
                over_quota=confirmed_total > d.license_quota,
                grades=grade_rows,
            )
        )

    return RegistrationSummaryResponse(
        grades=list(REGISTRATION_GRADES), departments=out
    )
