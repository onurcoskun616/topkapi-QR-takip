"""Authentication / authorization dependencies."""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models import Session, User, UserRole, UserStatus, ensure_aware
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate the access token and its single-device session.

    Returns the user even when they are still ``pending`` (so the PWA can poll
    ``/me`` to learn it has been approved). ``disabled`` accounts have their
    sessions deleted on disable, so they cannot reach here.
    """
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
        session_id = int(payload["sid"])
    except (JWTError, KeyError, ValueError, TypeError):
        raise _credentials_exc

    user = await db.get(User, user_id)
    if user is None or user.status == UserStatus.disabled:
        raise _credentials_exc

    # Enforce single-device: the access token's session must still be the
    # account's active one. A newer login/registration on another device deletes
    # this row, so the old device is rejected on its next request.
    session = await db.get(Session, session_id)
    if (
        session is None
        or session.user_id != user.id
        or session.revoked
        or ensure_aware(session.expires_at) <= datetime.now(timezone.utc)
    ):
        raise _credentials_exc

    return user


async def get_current_active_staff(
    user: User = Depends(get_current_user),
) -> User:
    """A staff member whose account has been approved (may scan / see own logs)."""
    if user.status != UserStatus.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hesabınız müdür onayı bekliyor.",
        )
    return user


async def get_current_manager(
    user: User = Depends(get_current_user),
) -> User:
    """A campus director or head-office user (management endpoints)."""
    if user.role not in (UserRole.campus_director, UserRole.hq):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için yönetici yetkisi gerekir.",
        )
    return user


async def get_current_hq(
    user: User = Depends(get_current_user),
) -> User:
    """A head-office (genel merkez) user only."""
    if user.role != UserRole.hq:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem yalnızca genel merkez yetkisindedir.",
        )
    return user
