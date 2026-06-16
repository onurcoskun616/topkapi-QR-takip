"""Pydantic request/response models."""
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from .models import (
    AttendanceSource,
    AttendanceStatus,
    AttendanceType,
    LeaveStatus,
    UserRole,
    UserStatus,
)


# --------------------------------------------------------------------------- #
# Campus
# --------------------------------------------------------------------------- #
class CampusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    shift_start: time | None = None
    shift_end: time | None = None


class CampusShiftUpdate(BaseModel):
    """hq-only: set a campus' work-hours / shift schedule."""

    shift_start: time
    shift_end: time


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
    source: AttendanceSource
    note: str | None = None


class AttendanceLogWithUser(AttendanceLogResponse):
    user_full_name: str
    campus_name: str | None = None
    recorded_by_name: str | None = None


class ManualAttendanceCreate(BaseModel):
    """Director/hq gap-fill entry — phone died, or the staff member forgot to
    scan. Strictly additive: there is no endpoint to edit/delete a real
    ``qr_scan`` row, so this can never overwrite real scan data."""

    user_id: int
    type: AttendanceType
    date: date
    time: time
    note: str | None = Field(default=None, max_length=255)


# --------------------------------------------------------------------------- #
# Leave / absence records
# --------------------------------------------------------------------------- #
class LeaveRecordCreate(BaseModel):
    user_id: int
    leave_type: str = Field(min_length=2, max_length=80)
    start_date: date
    end_date: date
    note: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _check_range(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date, start_date'den önce olamaz.")
        return self


class LeaveRecordUpdate(BaseModel):
    """Correct a leave record — e.g. shorten the range because the staff
    member actually showed up, or fix the wrong reason/type."""

    leave_type: str | None = Field(default=None, min_length=2, max_length=80)
    start_date: date | None = None
    end_date: date | None = None
    note: str | None = Field(default=None, max_length=255)
    status: LeaveStatus | None = None


class LeaveRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    user_full_name: str
    campus_name: str | None = None
    leave_type: str
    start_date: date
    end_date: date
    note: str | None = None
    status: LeaveStatus
    created_by_name: str | None = None
    created_at: datetime


class LeaveTypesResponse(BaseModel):
    suggested: list[str]


# --------------------------------------------------------------------------- #
# Reports — late / early-leave rankings, absence detail + aggregate stats
# --------------------------------------------------------------------------- #
class LateRankingEntry(BaseModel):
    user_id: int
    full_name: str
    campus_name: str | None = None
    late_days: int
    average_late_minutes: float


class EarlyLeaveRankingEntry(BaseModel):
    user_id: int
    full_name: str
    campus_name: str | None = None
    early_leave_days: int
    average_early_minutes: float


class AbsenceDayEntry(BaseModel):
    """One staff member's status for one calendar day in the range — the
    report never silently skips a day: it is always 'present', a named leave
    type, or 'unresolved' (durum girilmedi) so a gap can't go unnoticed."""

    user_id: int
    full_name: str
    campus_name: str | None = None
    date: date
    status: str  # "present" | <leave_type> | "unresolved"
    leave_record_id: int | None = None


class AbsenceReasonStat(BaseModel):
    leave_type: str
    day_count: int
    staff_count: int


class AbsenceTotalEntry(BaseModel):
    user_id: int
    full_name: str
    campus_name: str | None = None
    absent_days: int
    unresolved_days: int
    by_reason: dict[str, int]


class AbsenceSummaryResponse(BaseModel):
    start_date: date
    end_date: date
    by_reason: list[AbsenceReasonStat]
    totals_by_staff: list[AbsenceTotalEntry]
    unresolved_count: int


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
