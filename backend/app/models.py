"""ORM models for the attendance system."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Timezone-aware UTC now — the single source of truth for server time."""
    return datetime.now(timezone.utc)


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Treat a naive datetime as UTC.

    Postgres (the production driver) returns timezone-aware datetimes, but this
    guards comparisons against any backend/driver that hands back naive values.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class UserRole(str, enum.Enum):
    """Three-level hierarchy.

    * ``staff``           — teachers/personnel; passwordless, device-bound, scan QR.
    * ``campus_director`` — runs one campus: approves staff, resets devices, sees
                            that campus' reports (email + password login).
    * ``hq``              — head office: sees every campus, manages directors and
                            campuses (email + password login).
    """

    staff = "staff"
    campus_director = "campus_director"
    hq = "hq"


class UserStatus(str, enum.Enum):
    """Lifecycle of a staff account (managers are created already active)."""

    pending = "pending"   # self-registered, waiting for director approval
    active = "active"     # approved — may scan
    disabled = "disabled"  # deactivated by a manager


class AttendanceType(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class AttendanceStatus(str, enum.Enum):
    valid = "valid"
    auto_closed_by_system = "auto_closed_by_system"


class Campus(Base):
    """A physical campus (İkitelli OSB, İstanbul OSB, Esenyurt, Kıraç, Çorlu)."""

    __tablename__ = "campuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    users: Mapped[list["User"]] = relationship(back_populates="campus")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Staff identity is the phone number (passwordless, device-bound). Managers
    # leave it NULL. Postgres permits many NULLs under a UNIQUE constraint.
    phone: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True
    )
    # Managers (director / hq) log in with email + password; staff leave these NULL.
    email: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Staff-only profile fields collected at self-registration.
    job_title: Mapped[str | None] = mapped_column(String(80), nullable=True)   # görev
    branch: Mapped[str | None] = mapped_column(String(80), nullable=True)      # branş

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.staff, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"),
        default=UserStatus.pending,
        nullable=False,
    )

    # Staff and directors belong to one campus; hq is campus-wide (NULL).
    campus_id: Mapped[int | None] = mapped_column(
        ForeignKey("campuses.id", ondelete="RESTRICT"), index=True, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    campus: Mapped["Campus | None"] = relationship(back_populates="users")
    logs: Mapped[list["AttendanceLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scan_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    type: Mapped[AttendanceType] = mapped_column(
        Enum(AttendanceType, name="attendance_type"), nullable=False
    )
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus, name="attendance_status"),
        default=AttendanceStatus.valid,
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="logs")

    __table_args__ = (
        Index("ix_attendance_user_time", "user_id", "scan_time"),
    )


class Session(Base):
    """A login session bound to a single device.

    Enforces the "one active device per account" rule: on every successful
    login/registration the user's existing sessions are deleted and a fresh row
    is created. The long-lived refresh token references this row by id (``sid``);
    a session that is missing, revoked or expired invalidates both the refresh
    token and any still-valid access token carrying its ``sid``.

    A campus director can delete a staff member's session ("cihaz sıfırlama") so
    the staff member can re-bind a new phone to the same (phone-number) identity.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # SHA-256 of the device fingerprint supplied at login; compared on refresh.
    device_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # SHA-256 of the issued refresh token (raw token never stored).
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    revoked: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship()


class UsedQrToken(Base):
    """Replay-protection ledger.

    Each kiosk QR token carries a unique ``jti``. The first successful scan
    records the jti here so the *same* QR image (e.g. a photo of the tablet)
    cannot be reused by a second device within its 15-second validity window.
    """

    __tablename__ = "used_qr_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
