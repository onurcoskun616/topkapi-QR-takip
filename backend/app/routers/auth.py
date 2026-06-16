"""Authentication routes: login + current-user, plus admin user creation."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_admin, get_current_user
from ..models import User
from ..schemas import (
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Pre-computed once at import so the login path performs an equal-cost bcrypt
# check even for non-existent emails (defends against timing-based enumeration).
_DUMMY_PASSWORD_HASH = hash_password("topkapi-invalid-login-placeholder")


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

    token = create_access_token(user_id=user.id, role=user.role.value)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


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
