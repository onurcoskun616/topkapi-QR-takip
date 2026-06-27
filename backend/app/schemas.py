"""Pydantic request/response models."""
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from .models import (
    AttendanceSource,
    AttendanceStatus,
    AttendanceType,
    LeaveStatus,
    REGISTRATION_GRADES,
    RegistrationStatus,
    UserRole,
    UserStatus,
)
from .services import validate_tc_kimlik


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
    latitude: float | None = None
    longitude: float | None = None
    geofence_radius_m: int | None = None


class CampusShiftUpdate(BaseModel):
    """hq-only: set a campus' work-hours / shift schedule."""

    shift_start: time
    shift_end: time


class CampusLocationUpdate(BaseModel):
    """hq-only: set a campus' geofence (coordinates + allowed radius in metres).

    Send ``latitude``/``longitude`` as null to turn geofencing off for the
    campus (scans are then accepted without a location check, as before).
    """

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geofence_radius_m: int = Field(default=500, ge=50, le=20000)


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
    birth_date: date                                      # doğum tarihi
    # TC Kimlik No — a third identity factor cross-checked against phone +
    # device at registration, so an account can't be taken over by knowing
    # only the phone number.
    tc_kimlik_no: str = Field(min_length=11, max_length=11)
    campus_id: int
    device_fingerprint: str = Field(min_length=8, max_length=256)

    @model_validator(mode="after")
    def _check_tc_kimlik(self):
        if not validate_tc_kimlik(self.tc_kimlik_no):
            raise ValueError("Geçersiz TC kimlik numarası.")
        return self


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
    birth_date: date | None = None
    # Per-person working days as ISO weekday numbers (1=Mon … 7=Sun). ``None``
    # means "not configured" (the standard Mon–Fri week applies in reports).
    working_days: list[int] | None = None
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


class DirectorPasswordUpdate(BaseModel):
    """hq resets a director's password (e.g. they forgot it)."""

    password: str = Field(min_length=8, max_length=128)


class SelfPasswordChange(BaseModel):
    """A logged-in manager (director or hq) changes their own password."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class StaffBulkRow(BaseModel):
    """One staff member in a bulk import (e.g. start-of-year roster upload).

    Created directly as an ``active`` account with no bound device: the staff
    member binds their phone later by self-registering from the PWA with the
    *same* phone number (the re-claim path), keeping their imported profile."""

    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=32)
    job_title: str = Field(min_length=2, max_length=80)
    branch: str = Field(min_length=1, max_length=80)
    birth_date: date | None = None
    # hq may target a campus per row; a director is always pinned to their own.
    campus_id: int | None = None


class StaffBulkCreate(BaseModel):
    rows: list[StaffBulkRow] = Field(min_length=1, max_length=500)
    # hq default campus for rows that don't carry their own; ignored for a
    # director (every row lands on their campus).
    campus_id: int | None = None


class StaffBulkRowResult(BaseModel):
    full_name: str
    phone: str
    created: bool
    reason: str | None = None  # why a row was skipped (e.g. duplicate phone)


class StaffBulkResult(BaseModel):
    created_count: int
    skipped_count: int
    results: list[StaffBulkRowResult]


class StaffUpdate(BaseModel):
    """Optional manager correction of a staff profile (e.g. wrong campus).

    ``working_days`` is treated specially: omit it to leave the schedule
    untouched, send ``[]`` or ``null`` to clear it back to the default Mon–Fri
    week, or send a list of ISO weekday numbers (1=Mon … 7=Sun) to set a custom
    rotational schedule. Presence is detected via ``model_fields_set``.
    """

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    job_title: str | None = Field(default=None, min_length=2, max_length=80)
    branch: str | None = Field(default=None, min_length=1, max_length=80)
    birth_date: date | None = None
    working_days: list[int] | None = Field(default=None)
    campus_id: int | None = None

    @model_validator(mode="after")
    def _check_working_days(self):
        if self.working_days:
            for d in self.working_days:
                if not 1 <= d <= 7:
                    raise ValueError("working_days 1–7 (Pzt–Paz) aralığında olmalı.")
        return self


# --------------------------------------------------------------------------- #
# QR
# --------------------------------------------------------------------------- #
class QrTokenResponse(BaseModel):
    token: str
    jti: str
    issued_at: datetime
    expires_at: datetime
    ttl_seconds: int
    server_time: datetime


class QrTokenStatusResponse(BaseModel):
    used: bool


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #
class ScanRequest(BaseModel):
    qr_token: str = Field(min_length=1)
    # Phone location at scan time, for campus geofencing. Null when the device
    # couldn't provide a fix (permission denied / GPS off / no signal); the
    # server then rejects the scan for any campus that has geofencing enabled.
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0)


class ScanResponse(BaseModel):
    success: bool
    type: AttendanceType
    message: str
    scan_time: datetime
    user_full_name: str


# --------------------------------------------------------------------------- #
# Kiosk feed — tablet confirmation + birthday celebration
# --------------------------------------------------------------------------- #
class RecentScan(BaseModel):
    """A recent successful QR scan on a campus, polled by the kiosk so the
    tablet can confirm it (green "Giriş/Çıkış başarılı"). ``birthday`` marks the
    staff member's first IN of the day on their birthday, which the tablet
    celebrates instead of merely confirming."""

    log_id: int
    user_id: int
    full_name: str
    type: AttendanceType
    scan_time: datetime
    birthday: bool = False


class RecentScansResponse(BaseModel):
    scans: list[RecentScan]


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


class StaffLeaveRequestCreate(BaseModel):
    """A staff member's own leave request from the PWA. They pick the leave
    *kind* (Ücretli/Ücretsiz izin, Sağlık raporu, …) and a date range; it lands
    as ``requested`` for their campus director to approve or reject. It does not
    block scanning until a manager approves it."""

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
    # True when the staff member opened this themselves from the PWA (a request
    # awaiting/decided by a manager), as opposed to a director-created record.
    self_requested: bool = False
    created_by_name: str | None = None
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class LeaveTypesResponse(BaseModel):
    suggested: list[str]


# --------------------------------------------------------------------------- #
# Holidays / official closures
# --------------------------------------------------------------------------- #
class HolidayCreate(BaseModel):
    date: date
    name: str = Field(min_length=2, max_length=120)
    # None == applies to all campuses (national holiday). hq may target one
    # campus; a director is always pinned to their own campus by the router.
    campus_id: int | None = None


class HolidayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    name: str
    campus_id: int | None = None
    campus_name: str | None = None
    created_at: datetime


# --------------------------------------------------------------------------- #
# Announcements — full-screen kiosk notices (text and/or image)
# --------------------------------------------------------------------------- #
class AnnouncementResponse(BaseModel):
    """Admin-panel view of a notice (metadata only — image/video fetched separately)."""

    id: int
    title: str | None = None
    body: str | None = None
    has_image: bool = False
    image_url: str | None = None  # API path; the client prepends the API base
    has_video: bool = False
    video_url: str | None = None  # API path; the client prepends the API base
    campus_id: int | None = None
    campus_name: str | None = None
    active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    created_at: datetime


class AnnouncementActiveUpdate(BaseModel):
    active: bool


class KioskAnnouncement(BaseModel):
    """A single notice the kiosk should display right now."""

    id: int
    title: str | None = None
    body: str | None = None
    image_url: str | None = None  # API path; the client prepends the API base
    video_url: str | None = None  # API path; the client prepends the API base


class KioskAnnouncementsResponse(BaseModel):
    announcements: list[KioskAnnouncement]


# --------------------------------------------------------------------------- #
# Reports — late / early-leave rankings, absence detail + aggregate stats
# --------------------------------------------------------------------------- #
class LateRankingEntry(BaseModel):
    user_id: int
    full_name: str
    job_title: str | None = None   # görev
    branch: str | None = None      # branş
    campus_name: str | None = None
    late_days: int
    average_late_minutes: float


class EarlyLeaveRankingEntry(BaseModel):
    user_id: int
    full_name: str
    job_title: str | None = None   # görev
    branch: str | None = None      # branş
    campus_name: str | None = None
    early_leave_days: int
    average_early_minutes: float


class LateArrivalEntry(BaseModel):
    """One single late arrival event (one staff member, one day), listed by
    date + clock time rather than aggregated — so a manager can read exactly
    who came in late, on which day, and at what time."""

    user_id: int
    full_name: str
    job_title: str | None = None   # görev
    branch: str | None = None      # branş
    campus_name: str | None = None
    date: date
    arrival_time: str   # local clock time of the first IN, "HH:MM"
    shift_start: str    # campus shift start that day, "HH:MM"
    minutes_late: int


class EarlyLeaveEntry(BaseModel):
    """One single early-leave event (one staff member, one day), listed by
    date + clock time rather than aggregated."""

    user_id: int
    full_name: str
    job_title: str | None = None   # görev
    branch: str | None = None      # branş
    campus_name: str | None = None
    date: date
    leave_time: str     # local clock time of the last OUT, "HH:MM"
    shift_end: str      # campus shift end that day, "HH:MM"
    minutes_early: int


class AbsenceDayEntry(BaseModel):
    """One staff member's status for one calendar day in the range — the
    report never silently skips a day: it is always 'present', a named leave
    type, or 'unresolved' (durum girilmedi) so a gap can't go unnoticed."""

    user_id: int
    full_name: str
    job_title: str | None = None   # görev
    branch: str | None = None      # branş
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
    job_title: str | None = None   # görev
    branch: str | None = None      # branş
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


class UnresolvedReminderResponse(BaseModel):
    """Recent absence days still missing a status (durum girilmedi) — the
    manager's "you have things to resolve" reminder, over a trailing window
    ending yesterday (today isn't over yet)."""

    start_date: date
    end_date: date
    unresolved_count: int
    entries: list[AbsenceDayEntry]


class MonthlyHoursEntry(BaseModel):
    """One staff member's monthly totals for payroll/puantaj: worked hours
    (sum of first-IN→last-OUT each day), days present, cumulative late
    minutes, and absent/leave day counts over their scheduled work days."""

    user_id: int
    full_name: str
    job_title: str | None = None   # görev
    branch: str | None = None      # branş
    campus_name: str | None = None
    expected_days: int       # days they were scheduled to work this month
    present_days: int        # days with at least one scan
    worked_days: int         # days with a complete IN+OUT pair
    total_hours: float       # Σ (last OUT − first IN) across days, in hours
    total_late_minutes: int  # cumulative lateness vs campus shift start
    absent_days: int         # scheduled days with no scan and no leave
    leave_days: int          # scheduled days covered by an active leave


class MonthlyHoursResponse(BaseModel):
    year: int
    month: int
    start_date: date
    end_date: date
    entries: list[MonthlyHoursEntry]


class DailyTrendEntry(BaseModel):
    """Aggregate attendance for one calendar day across all in-scope staff —
    the building block for the dashboard/report trend chart."""

    date: date
    expected: int      # staff expected to work that day (after schedule + holidays)
    present: int       # of those, who had at least one scan
    on_leave: int      # of those, covered by an active leave record
    unresolved: int    # absent with no leave (= durum girilmedi)


class DailyTrendResponse(BaseModel):
    start_date: date
    end_date: date
    entries: list[DailyTrendEntry]
    total_expected: int
    total_present: int
    total_on_leave: int
    total_unresolved: int


class RiskStaffEntry(BaseModel):
    """One flagged staff member in the early-warning panel: their late /
    early-leave / unresolved-absence counts for the range, a numeric risk
    score, a level, and human-readable reasons (flags)."""

    user_id: int
    full_name: str
    job_title: str | None = None   # görev
    branch: str | None = None      # branş
    campus_name: str | None = None
    late_days: int
    early_leave_days: int
    unresolved_days: int
    score: int
    level: str             # "medium" | "high"
    flags: list[str]


class RiskReportResponse(BaseModel):
    start_date: date
    end_date: date
    high_count: int
    medium_count: int
    entries: list[RiskStaffEntry]
    # Echo the thresholds in effect so the panel can explain what it flagged.
    late_threshold: int
    early_leave_threshold: int
    unresolved_threshold: int


class ForgotCheckoutEntry(BaseModel):
    """A staff member still 'inside' (last log today is IN) whose campus shift
    has already ended — they likely forgot to scan out and will otherwise be
    auto-closed at 23:59."""

    user_id: int
    full_name: str
    campus_name: str | None = None
    since: datetime           # the open IN time
    minutes_overdue: int      # minutes past campus shift_end


class ForgotCheckoutResponse(BaseModel):
    as_of: datetime
    entries: list[ForgotCheckoutEntry]


# --------------------------------------------------------------------------- #
# Location alerts — far-from-campus QR scan attempts (geofence violations)
# --------------------------------------------------------------------------- #
class LocationAlertEntry(BaseModel):
    id: int
    user_id: int
    full_name: str
    job_title: str | None = None
    branch: str | None = None
    campus_name: str | None = None
    distance_m: int
    accuracy_m: int | None = None
    latitude: float
    longitude: float
    maps_url: str          # quick link to open the reported spot on a map
    created_at: datetime


class LocationAlertsResponse(BaseModel):
    count: int
    entries: list[LocationAlertEntry]


class MyStatusResponse(BaseModel):
    """A staff member's own live attendance state, so the PWA can remind them
    to scan out when their shift has ended but they're still marked inside."""

    currently_in: bool
    since: datetime | None = None
    should_check_out: bool = False  # inside AND past campus shift end
    minutes_overdue: int | None = None


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


# --------------------------------------------------------------------------- #
# Student registration — departments, quotas, targets, registrations
# --------------------------------------------------------------------------- #
class RegistrationTargetItem(BaseModel):
    """A department's internal/external goal for one grade (9/10/11/12)."""

    grade: int = Field(ge=9, le=12)
    internal_target: int = Field(default=0, ge=0)
    external_target: int = Field(default=0, ge=0)


class DepartmentCreate(BaseModel):
    """hq-only: create a campus department with its MEB license quota."""

    campus_id: int
    name: str = Field(min_length=1, max_length=120)
    license_quota: int = Field(default=0, ge=0)


class DepartmentUpdate(BaseModel):
    """hq-only: rename a department or change its license quota."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    license_quota: int | None = Field(default=None, ge=0)


class DepartmentTargetsUpdate(BaseModel):
    """hq-only: replace the per-grade registration targets for a department.

    Grades omitted from the list are cleared back to 0/0. At most one entry per
    grade is allowed.
    """

    targets: list[RegistrationTargetItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_unique_grades(self):
        grades = [t.grade for t in self.targets]
        if len(grades) != len(set(grades)):
            raise ValueError("Her sınıf için en fazla bir hedef girilebilir.")
        return self


class DepartmentResponse(BaseModel):
    id: int
    campus_id: int
    campus_name: str | None = None
    name: str
    license_quota: int
    targets: list[RegistrationTargetItem]
    # Confirmed (registered + approved) registrations currently held, and how
    # many license slots remain.
    confirmed_count: int = 0
    remaining_quota: int = 0
    created_at: datetime


class StudentRegistrationCreate(BaseModel):
    department_id: int
    full_name: str = Field(min_length=2, max_length=120)
    grade: int = Field(ge=9, le=12)
    section: str | None = Field(default=None, max_length=20)
    arrival_channel: str = Field(min_length=1, max_length=80)
    status: RegistrationStatus = RegistrationStatus.prospective
    approved: bool = False


class StudentRegistrationUpdate(BaseModel):
    """Partial update; only provided fields change. ``approved`` is handled via
    the dedicated approve/unapprove endpoints, not here."""

    department_id: int | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    grade: int | None = Field(default=None, ge=9, le=12)
    section: str | None = Field(default=None, max_length=20)
    arrival_channel: str | None = Field(default=None, min_length=1, max_length=80)
    status: RegistrationStatus | None = None


class StudentRegistrationResponse(BaseModel):
    id: int
    campus_id: int
    campus_name: str | None = None
    department_id: int
    department_name: str | None = None
    full_name: str
    grade: int
    section: str | None = None
    arrival_channel: str
    # Derived: True when the arrival channel is the internal one (iç kayıt).
    is_internal: bool
    status: RegistrationStatus
    approved: bool
    # True when this record currently counts toward the quota/targets
    # (status == registered AND approved).
    counts_toward_target: bool
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    created_at: datetime


class RegistrationGradeSummary(BaseModel):
    """One (department, grade) row of the registration dashboard."""

    grade: int
    internal_target: int
    external_target: int
    internal_count: int
    external_count: int


class RegistrationDepartmentSummary(BaseModel):
    department_id: int
    department_name: str
    campus_id: int
    campus_name: str | None = None
    license_quota: int
    confirmed_count: int      # registered + approved, all grades
    remaining_quota: int      # license_quota − confirmed_count (never below 0)
    over_quota: bool          # confirmed_count > license_quota (data sanity flag)
    grades: list[RegistrationGradeSummary]


class RegistrationSummaryResponse(BaseModel):
    grades: list[int] = Field(default_factory=lambda: list(REGISTRATION_GRADES))
    departments: list[RegistrationDepartmentSummary]


# --------------------------------------------------------------------------- #
# Web Push (notifications)
# --------------------------------------------------------------------------- #
class PushPublicKeyResponse(BaseModel):
    """What the PWA needs to subscribe: whether push is enabled server-side and
    the VAPID public key (browser ``applicationServerKey``)."""

    enabled: bool
    public_key: str | None = None


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionRequest(BaseModel):
    """Mirrors the browser ``PushSubscription.toJSON()`` shape."""

    endpoint: str
    keys: PushKeys


class PushSubscriptionResult(BaseModel):
    subscribed: bool
