"""Helpers that turn ORM rows into API response models.

Kept separate so routers stay terse and async lazy-loading pitfalls (accessing
``user.campus`` outside an eager load) are avoided — campus_name is always passed
in explicitly by the caller.
"""
from .models import User
from .schemas import UserResponse


def to_user_response(
    user: User, *, campus_name: str | None = None, has_device: bool = False
) -> UserResponse:
    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        phone=user.phone,
        email=user.email,
        job_title=user.job_title,
        branch=user.branch,
        campus_id=user.campus_id,
        campus_name=campus_name,
        has_device=has_device,
        created_at=user.created_at,
    )
