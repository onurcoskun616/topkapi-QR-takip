"""Pydantic request/response models."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import AttendanceStatus, AttendanceType, UserRole, UserStatus


# --------------------------------------------------------------------------- #
# Campus
# --------------------------------------------------------------------------- #
class CampusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str


# --------------------------------------------------------------------------- #
# Auth — staff (passwordless, device-bound) and managers (email + password)
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    """Staff self-registration from the PWA. The phone number is the permanent
    identity; the device that registers becomes the bound device."""

    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=32)
    job_title: str = Field(min_length=2, max_length=80)   # görev
    branch: str = Field(min_length=1, max_length=80)      # branş
    campus_id: int
    device_fingerprint: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    """Manager (director / hq) login."""

    email: EmailStr
    password: str = Field(min_length=1)
    device_fingerprint: str = Field(min_length=8, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)
    device_fingerprint: str = Field(min_length=8, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_in: int  # seconds until the access token expires
    user: "UserResponse"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    access_expires_in: int
    user: "UserResponse"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    role: UserRole
    status: UserStatus
    phone: str | None = None
    email: EmailStr | None = None
    job_title: str | None = None
    branch: str | None = None
    campus_id: int | None = None
    campus_name: str | None = None
    has_device: bool = False
    created_at: datetime


# --------------------------------------------------------------------------- #
# Management — directors create/approve, hq manages directors
# --------------------------------------------------------------------------- #
class DirectorCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    campus_id: int


class StaffUpdate(BaseModel):
    """Optional manager correction of a staff profile (e.g. wrong campus)."""

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    job_title: str | None = Field(default=None, min_length=2, max_length=80)
    branch: str | None = Field(default=None, min_length=1, max_length=80)
    campus_id: int | None = None


# --------------------------------------------------------------------------- #
# QR
# --------------------------------------------------------------------------- #
class QrTokenResponse(BaseModel):
    token: str
    issued_at: datetime
    expires_at: datetime
    ttl_seconds: int
    server_time: datetime


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #
class ScanRequest(BaseModel):
    qr_token: str = Field(min_length=1)


class ScanResponse(BaseModel):
    success: bool
    type: AttendanceType
    message: str
    scan_time: datetime
    user_full_name: str


# --------------------------------------------------------------------------- #
# Logs
# --------------------------------------------------------------------------- #
class AttendanceLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    scan_time: datetime
    type: AttendanceType
    status: AttendanceStatus


class AttendanceLogWithUser(AttendanceLogResponse):
    user_full_name: str
    campus_name: str | None = None


# --------------------------------------------------------------------------- #
# Reporting / presence
# --------------------------------------------------------------------------- #
class PresenceEntry(BaseModel):
    user_id: int
    full_name: str
    campus_name: str | None = None
    since: datetime


class TodaySummary(BaseModel):
    date: date
    active_today: int
    currently_in_count: int
    currently_in: list[PresenceEntry]
