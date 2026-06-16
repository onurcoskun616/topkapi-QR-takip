"""Shared campus/staff scoping helpers for manager-facing endpoints.

Centralised so every router (staff management, manual attendance, leave
records, reports) enforces the same rule: a campus director only ever
touches their own campus; hq may see/filter across all of them.
"""
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User, UserRole


def scope_campus_id(manager: User, requested_campus_id: int | None) -> int | None:
    """Resolve which campus the manager is allowed to query/act on.

    Directors are pinned to their own campus; hq may pass an optional filter
    (``None`` == all campuses).
    """
    if manager.role == UserRole.campus_director:
        return manager.campus_id
    return requested_campus_id


async def load_scoped_staff(db: AsyncSession, manager: User, staff_id: int) -> User:
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
