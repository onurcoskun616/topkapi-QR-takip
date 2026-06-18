"""Authentication routes.

Two credential models share one device-bound, dual-token session system:

  * **Staff (personnel)** — passwordless. They self-register from the PWA with
    their profile + phone number + TC kimlik no; the phone number is their
    permanent identity, and the registering device + TC kimlik no are both
    locked to it. New accounts start ``pending`` until a campus director
    approves them. A new phone can only re-claim the identity after a director
    clears the old device ("cihaz sıfırlama"), and the TC kimlik no submitted
    must always match the one already on file.
  * **Managers (director / hq)** — classic email + password login.

Both paths then use:
  * **refresh** — silent morning refresh: refresh token + matching device
    fingerprint → fresh access token, no re-entry.
  * **logout**  — revoke the current session.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import ratelimit
from ..config import settings
from ..database import get_db
from ..deps import get_current_manager, get_current_user, oauth2_scheme
from ..models import Campus, Session, User, UserRole, UserStatus, ensure_aware
from ..schemas import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SelfPasswordChange,
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
from ..services import describe_phone_error, normalize_phone

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


async def _device_belongs_to_other(
    db: AsyncSession, device_fp_hash: str, exclude_user_id: int | None
) -> bool:
    """True if this device is already tied to a *different* account.

    Enforces "one device → one employee": a single phone must not be usable to
    register/operate two people. We check both the persistent binding on the
    account (``User.device_fp_hash``) and any live session — the latter also
    covers accounts bound before the persistent field existed. ``exclude_user_id``
    skips the account currently (re-)claiming this same device.
    """
    user_query = select(User.id).where(User.device_fp_hash == device_fp_hash)
    if exclude_user_id is not None:
        user_query = user_query.where(User.id != exclude_user_id)
    if (await db.execute(user_query)).first() is not None:
        return True

    now = datetime.now(timezone.utc)
    session_query = select(Session.id).where(
        Session.device_fingerprint == device_fp_hash,
        Session.revoked.is_(False),
        Session.expires_at > now,
    )
    if exclude_user_id is not None:
        session_query = session_query.where(Session.user_id != exclude_user_id)
    return (await db.execute(session_query)).first() is not None


async def _bound_device(db: AsyncSession, user: User) -> str | None:
    """The device fingerprint hash this account is bound to, or None.

    Prefers the persistent ``User.device_fp_hash``; falls back to a live session's
    fingerprint so accounts bound before the persistent field existed are still
    protected (and get back-filled on their next registration).
    """
    if user.device_fp_hash:
        return user.device_fp_hash
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Session.device_fingerprint)
        .where(
            Session.user_id == user.id,
            Session.revoked.is_(False),
            Session.expires_at > now,
        )
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None



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
    """Staff self-registration (and first-time device binding) — passwordless.

    Identity = phone number, TC kimlik no, **and** device — all three must
    agree with what's already on file:

    * New phone number  → create a ``pending`` account and bind TC kimlik + device.
    * Known phone number **not yet bound** to a device (fresh / bulk-imported, or
      a manager reset it) → bind TC kimlik + this device, keeping history & approval.
    * Known phone number already bound to **this same** device and TC kimlik →
      re-issue (e.g. the app was reinstalled).
    * Known phone number bound to a **different** device, or a TC kimlik that
      doesn't match the one on file → refuse; only a manager's "Cihazı Sıfırla"
      frees the account. This stops anyone from claiming someone else's identity
      just by knowing their phone number, and stops a stolen/guessed TC kimlik
      from being reused on a different phone+device.
    """
    campus = await db.get(Campus, payload.campus_id)
    if campus is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz kampüs seçimi."
        )

    phone = normalize_phone(payload.phone)
    phone_error = describe_phone_error(phone)
    if phone_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=phone_error)
    tc_kimlik_no = payload.tc_kimlik_no

    existing = await db.execute(select(User).where(User.phone == phone))
    user = existing.scalar_one_or_none()

    # One TC kimlik no → one employee: refuse if this national ID is already
    # tied to a *different* account (blocks reusing someone else's identity
    # number on a new phone/device).
    tc_query = select(User.id).where(User.tc_kimlik_no == tc_kimlik_no)
    if user is not None:
        tc_query = tc_query.where(User.id != user.id)
    if (await db.execute(tc_query)).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Bu TC kimlik numarası başka bir hesaba kayıtlı. Müdürünüze "
                "başvurun."
            ),
        )

    # One device → one employee: refuse if this device is already tied to a
    # different account (blocks registering/operating a second person on one phone).
    device_fp_hash = sha256_hex(payload.device_fingerprint)
    if await _device_belongs_to_other(
        db, device_fp_hash, exclude_user_id=user.id if user is not None else None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Bu cihaz zaten başka bir personele tanımlı. Her personel kendi "
                "telefonuyla kayıt olmalıdır. Cihaz değişikliği için müdürünüzden "
                "cihaz sıfırlaması isteyin."
            ),
        )

    if user is not None:
        if user.role != UserRole.staff or user.status == UserStatus.disabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu telefon numarası kullanılamıyor. Müdürünüze başvurun.",
            )
        # Both must match: if this account is already bound to a device, only the
        # *same* device may re-register. A different one needs a manager reset.
        bound = await _bound_device(db, user)
        if bound is not None and bound != device_fp_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Bu telefon numarası başka bir cihaza tanımlı. Yeni telefon "
                    "için müdürünüzden cihaz sıfırlaması isteyin."
                ),
            )
        # TC kimlik must also agree with the one already on file — the third
        # leg of the phone + TC kimlik + device match.
        if user.tc_kimlik_no is not None and user.tc_kimlik_no != tc_kimlik_no:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Bu telefon numarası başka bir TC kimlik numarasına kayıtlı. "
                    "Müdürünüze başvurun."
                ),
            )
        # Re-claim / re-bind this device. Keep approval status & campus.
        user.device_fp_hash = device_fp_hash
        # Backfill fields that predate this record (bulk-imported, or before
        # the field existed) instead of overwriting an already-set value.
        if user.tc_kimlik_no is None:
            user.tc_kimlik_no = tc_kimlik_no
        if user.birth_date is None:
            user.birth_date = payload.birth_date
    else:
        user = User(
            full_name=payload.full_name.strip(),
            phone=phone,
            job_title=payload.job_title.strip(),
            branch=payload.branch.strip(),
            birth_date=payload.birth_date,
            tc_kimlik_no=tc_kimlik_no,
            role=UserRole.staff,
            status=UserStatus.pending,
            campus_id=campus.id,
            device_fp_hash=device_fp_hash,
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
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Manager (campus director / hq) login with email + password."""
    email = payload.email.lower()
    client_ip = request.client.host if request.client else "unknown"

    # Brute-force guard: refuse early while this (email, ip) is locked out.
    locked_for = ratelimit.is_locked(email, client_ip)
    if locked_for:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Çok fazla hatalı giriş denemesi. Lütfen "
                f"{max(1, locked_for // 60)} dakika sonra tekrar deneyin."
            ),
        )

    result = await db.execute(select(User).where(User.email == email))
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
        ratelimit.record_failure(email, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı.",
        )

    ratelimit.reset(email, client_ip)
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


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: SelfPasswordChange,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    """A manager (director / hq) changes their own password from the panel."""
    if not verify_password(payload.current_password, manager.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Mevcut şifre hatalı."
        )
    manager.password_hash = hash_password(payload.new_password)
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
