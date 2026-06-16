"""Authentication / authorization dependencies."""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models import Session, User, UserRole
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
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
        session_id = int(payload["sid"])
    except (JWTError, KeyError, ValueError, TypeError):
        raise _credentials_exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_exc

    # Enforce single-device: the access token's session must still be the
    # account's active one. A newer login on another device deletes this row,
    # so the old device is rejected on its next request.
    session = await db.get(Session, session_id)
    if (
        session is None
        or session.user_id != user.id
        or session.revoked
        or session.expires_at <= datetime.now(timezone.utc)
    ):
        raise _credentials_exc

    return user


async def get_current_admin(
    user: User = Depends(get_current_user),
) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
