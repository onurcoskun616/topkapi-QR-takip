"""Authentication routes for the device-bound, dual-token security model.

Flow:
  * **login**   — verify credentials, then revoke the account's previous
    sessions (single-device rule) and issue a 15-min access token plus a
    365-day refresh token bound to the supplied device fingerprint.
  * **refresh** — the PWA's silent morning refresh: present the refresh token
    + device fingerprint, get a fresh access token without re-entering a
    password. A fingerprint/session mismatch fails (stolen-token defence).
  * **logout**  — revoke the current session.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_admin, get_current_user, oauth2_scheme
from ..models import Session, User
from ..schemas import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from ..security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    sha256_hex,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Pre-computed once at import so the login path performs an equal-cost bcrypt
# check even for non-existent emails (defends against timing-based enumeration).
_DUMMY_PASSWORD_HASH = hash_password("topkapi-invalid-login-placeholder")

_access_ttl_seconds = settings.access_token_expire_minutes * 60


async def _issue_session(
    db: AsyncSession, user: User, device_fingerprint: str
) -> tuple[str, str]:
    """Create a fresh single-device session and return (access, refresh)."""
    # Single-device rule: drop every previous session for this account.
    await db.execute(delete(Session).where(Session.user_id == user.id))
    await db.flush()

    session = Session(
        user_id=user.id,
        device_fingerprint=sha256_hex(device_fingerprint),
        refresh_token_hash="",  # set below once we know the session id
        expires_at=datetime.now(timezone.utc),  # replaced below
    )
    db.add(session)
    await db.flush()  # assigns session.id

    refresh = create_refresh_token(user_id=user.id, session_id=session.id)
    session.refresh_token_hash = sha256_hex(refresh["token"])
    session.expires_at = refresh["expires_at"]

    access = create_access_token(
        user_id=user.id, role=user.role.value, session_id=session.id
    )
    await db.commit()
    return access, refresh["token"]


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()

    # Always run a bcrypt verification — against a dummy hash when the email is
    # unknown — so response time does not reveal whether an account exists.
    valid = verify_password(
        payload.password, user.password_hash if user else _DUMMY_PASSWORD_HASH
    )
    if not user or not valid or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access, refresh = await _issue_session(db, user, payload.device_fingerprint)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        access_expires_in=_access_ttl_seconds,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Silent refresh: exchange a valid refresh token + matching device
    fingerprint for a new access token. No password required."""
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Oturum geçersiz. Lütfen tekrar giriş yapın.",
    )

    try:
        claims = decode_refresh_token(payload.refresh_token)
        user_id = int(claims["sub"])
        session_id = int(claims["sid"])
    except (JWTError, KeyError, ValueError, TypeError):
        raise invalid

    session = await db.get(Session, session_id)
    now = datetime.now(timezone.utc)
    if (
        session is None
        or session.user_id != user_id
        or session.revoked
        or session.expires_at <= now
        # The presented refresh token must be the one bound to this session
        # (a login on another device replaced it).
        or session.refresh_token_hash != sha256_hex(payload.refresh_token)
        # The device must match the one the session was bound to at login.
        or session.device_fingerprint != sha256_hex(payload.device_fingerprint)
    ):
        raise invalid

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise invalid

    session.last_used_at = now
    access = create_access_token(
        user_id=user.id, role=user.role.value, session_id=session.id
    )
    await db.commit()
    return AccessTokenResponse(
        access_token=access,
        access_expires_in=_access_ttl_seconds,
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Revoke the session carried by the presented access token."""
    try:
        claims = decode_access_token(token)
        session_id = int(claims["sid"])
    except (JWTError, KeyError, ValueError, TypeError):
        return  # nothing to revoke / already invalid
    await db.execute(delete(Session).where(Session.id == session_id))
    await db.commit()


@router.get("/me", response_model=UserResponse)
async def me(current: User = Depends(get_current_user)):
    return current


@router.get(
    "/users",
    response_model=list[UserResponse],
    dependencies=[Depends(get_current_admin)],
)
async def list_users(db: AsyncSession = Depends(get_db)):
    """Admin-only: list all accounts (for the admin panel)."""
    result = await db.execute(select(User).order_by(User.full_name))
    return list(result.scalars().all())


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_admin)],
)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """Admin-only: register a new teacher/admin account."""
    email = payload.email.lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    user = User(
        full_name=payload.full_name,
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
