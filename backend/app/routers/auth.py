"""Authentication routes.

Two credential models share one device-bound, dual-token session system:

  * **Staff (personnel)** — passwordless. They self-register from the PWA with
    their profile + phone number; that phone number is their permanent identity
    and the registering device is locked to it. New accounts start ``pending``
    until a campus director approves them. A new phone can only re-claim the
    identity after a director clears the old device ("cihaz sıfırlama").
  * **Managers (director / hq)** — classic email + password login.

Both paths then use:
  * **refresh** — silent morning refresh: refresh token + matching device
    fingerprint → fresh access token, no re-entry.
  * **logout**  — revoke the current session.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, oauth2_scheme
from ..models import Campus, Session, User, UserRole, UserStatus, ensure_aware
from ..schemas import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
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
from ..serializers import to_user_response
from ..services import normalize_phone

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Pre-computed once at import so the login path performs an equal-cost bcrypt
# check even for non-existent emails (defends against timing-based enumeration).
_DUMMY_PASSWORD_HASH = hash_password("topkapi-invalid-login-placeholder")

_access_ttl_seconds = settings.access_token_expire_minutes * 60


async def _campus_name(db: AsyncSession, campus_id: int | None) -> str | None:
    if campus_id is None:
        return None
    campus = await db.get(Campus, campus_id)
    return campus.name if campus else None


async def _has_active_session(db: AsyncSession, user_id: int) -> bool:
    """True if the account currently has a non-expired, non-revoked device bound."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Session.id).where(
            Session.user_id == user_id,
            Session.revoked.is_(False),
            Session.expires_at > now,
        )
    )
    return result.first() is not None


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


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Staff self-registration (and new-phone re-claim) — passwordless.

    * New phone number  → create a ``pending`` account on the chosen campus.
    * Known phone number with **no** bound device (a director reset it) →
      re-bind this device to the existing identity, keeping history & approval.
    * Known phone number that is still bound to a device → refuse; the staff
      member must ask their director to reset the old phone first.
    """
    campus = await db.get(Campus, payload.campus_id)
    if campus is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz kampüs seçimi."
        )

    phone = normalize_phone(payload.phone)
    if len(phone) < 7:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz telefon numarası."
        )

    existing = await db.execute(select(User).where(User.phone == phone))
    user = existing.scalar_one_or_none()

    if user is not None:
        if user.role != UserRole.staff or user.status == UserStatus.disabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu telefon numarası kullanılamıyor. Müdürünüze başvurun.",
            )
        if await _has_active_session(db, user.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Bu telefon numarası başka bir cihaza tanımlı. Yeni telefon "
                    "için müdürünüzden cihaz sıfırlaması isteyin."
                ),
            )
        # Re-claim: same identity, new device. Keep approval status & campus.
    else:
        user = User(
            full_name=payload.full_name.strip(),
            phone=phone,
            job_title=payload.job_title.strip(),
            branch=payload.branch.strip(),
            role=UserRole.staff,
            status=UserStatus.pending,
            campus_id=campus.id,
        )
        db.add(user)
        await db.flush()  # assigns user.id

    access, refresh = await _issue_session(db, user, payload.device_fingerprint)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        access_expires_in=_access_ttl_seconds,
        user=to_user_response(user, campus_name=campus.name, has_device=True),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Manager (campus director / hq) login with email + password."""
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()

    # Always run a bcrypt verification — against a dummy hash when the email is
    # unknown — so response time does not reveal whether an account exists.
    valid = verify_password(
        payload.password, user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH
    )
    if (
        not user
        or not user.password_hash
        or not valid
        or user.role not in (UserRole.campus_director, UserRole.hq)
        or user.status != UserStatus.active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı.",
        )

    access, refresh = await _issue_session(db, user, payload.device_fingerprint)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        access_expires_in=_access_ttl_seconds,
        user=to_user_response(
            user, campus_name=await _campus_name(db, user.campus_id), has_device=True
        ),
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
        or ensure_aware(session.expires_at) <= now
        # The presented refresh token must be the one bound to this session
        # (a login on another device replaced it).
        or session.refresh_token_hash != sha256_hex(payload.refresh_token)
        # The device must match the one the session was bound to at login.
        or session.device_fingerprint != sha256_hex(payload.device_fingerprint)
    ):
        raise invalid

    user = await db.get(User, user_id)
    if user is None or user.status == UserStatus.disabled:
        raise invalid

    session.last_used_at = now
    access = create_access_token(
        user_id=user.id, role=user.role.value, session_id=session.id
    )
    await db.commit()
    return AccessTokenResponse(
        access_token=access,
        access_expires_in=_access_ttl_seconds,
        user=to_user_response(
            user, campus_name=await _campus_name(db, user.campus_id), has_device=True
        ),
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
async def me(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return to_user_response(
        current,
        campus_name=await _campus_name(db, current.campus_id),
        has_device=True,
    )
