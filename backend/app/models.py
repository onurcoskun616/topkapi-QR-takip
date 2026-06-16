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


class UserRole(str, enum.Enum):
    teacher = "teacher"
    admin = "admin"


class AttendanceType(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class AttendanceStatus(str, enum.Enum):
    valid = "valid"
    auto_closed_by_system = "auto_closed_by_system"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.teacher, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

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


class UsedQrToken(Base):
    """Replay-protection ledger.

    Each kiosk QR token carries a unique ``jti``. The first successful scan
    records the jti here so the *same* QR image cannot be reused by a second
    device within its 15-second validity window.
    """

    __tablename__ = "used_qr_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
