"""ORM models for the attendance system."""
import enum
from datetime import date, datetime, time, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
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


class AttendanceSource(str, enum.Enum):
    """Where an attendance row came from — kept separate so reports can never
    confuse a real scan with a manager's manual gap-fill entry."""

    qr_scan = "qr_scan"
    director_manual = "director_manual"


class LeaveStatus(str, enum.Enum):
    requested = "requested"  # submitted by staff, awaiting director decision (does NOT block scanning)
    active = "active"        # approved/director-created — blocks scanning for the covered date range
    rejected = "rejected"    # staff request declined by a manager — blocks nothing
    cancelled = "cancelled"  # corrected/withdrawn — no longer blocks anything


# The four high-school grades (sınıf) that carry per-department registration
# targets (kayıt hedefi). Centralised so the model, the API and the reports all
# agree on which grades exist.
REGISTRATION_GRADES: tuple[int, ...] = (9, 10, 11, 12)

# The single arrival channel (Geliş Kanalı) that counts as an *internal*
# registration (iç kayıt). Every other channel is treated as external
# (dış kayıt). See ``app.services.is_internal_channel`` for the matcher.
INTERNAL_ARRIVAL_CHANNEL = "İç Kayıt"


class RegistrationStatus(str, enum.Enum):
    """Lifecycle of a student registration (öğrenci kayıt durumu).

    A registration only counts toward a department's license quota and its
    internal/external targets once it is ``registered`` **and** approved by a
    campus manager (see ``StudentRegistration.approved``).
    """

    prospective = "prospective"  # aday — görüşülüyor, henüz kayıt yapılmadı
    registered = "registered"    # kayıt yapıldı
    cancelled = "cancelled"      # iptal / vazgeçti


class Campus(Base):
    """A physical campus (İkitelli OSB, İstanbul OSB, Esenyurt, Kıraç, Çorlu)."""

    __tablename__ = "campuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)

    # Work-hours / shift schedule — only head office (hq) may set these
    # (enforced in the router, not here); directors have no write access.
    shift_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    shift_end: Mapped[time | None] = mapped_column(Time, nullable=True)

    # Geofence (konum doğrulaması): the campus' coordinates and the allowed
    # radius in metres. A staff QR scan is only accepted when the phone reports a
    # location within this radius of the campus. Geofencing is OFF until both
    # latitude and longitude are set — so campuses without coordinates keep
    # working exactly as before. ``geofence_radius_m`` defaults to 500.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_radius_m: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=500
    )

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
    # Turkish national identity number (TC Kimlik No), collected at self-
    # registration as a third binding factor alongside phone + device: a
    # mismatch with the value already on file blocks the attempt (see
    # auth.py register()), making it harder to take over an identity by only
    # knowing/guessing the phone number. Managers leave it NULL.
    tc_kimlik_no: Mapped[str | None] = mapped_column(String(11), nullable=True)
    # Birth date (staff self-registration). Only the month/day is used, to wish
    # the person a happy birthday on the kiosk when they scan in.
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Per-person working days, for staff who work a rotational/shift schedule
    # (not the standard Mon–Fri). Stored as a comma-separated list of ISO
    # weekday numbers (1=Monday … 7=Sunday), e.g. "1,2,3,4,6". ``NULL`` means
    # "not configured": reports fall back to the caller's weekday default.
    # Only managers may set this (görev rolü), via PATCH /api/staff/{id}.
    working_days: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # SHA-256 of the device fingerprint this staff account is permanently bound
    # to (set when the phone first binds a device at registration). Re-registering
    # the same phone number from a *different* device is refused unless a manager
    # clears this ("Cihazı Sıfırla"). Managers leave it NULL (they use passwords).
    # Persisted on the account — not only on the session — so the binding survives
    # logout/expiry and a phone number alone can never be re-claimed elsewhere.
    # A *unique* index (see __table_args__) makes "one device → one employee" a
    # hard database invariant: even a race of two simultaneous registrations from
    # the same phone can never bind it to two accounts. (NULLs stay distinct on
    # both PostgreSQL and SQLite, so managers/unbound staff are unaffected.)
    device_fp_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
        back_populates="user",
        foreign_keys="AttendanceLog.user_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # One device → one employee, enforced at the database level.
        Index("uq_users_device_fp_hash", "device_fp_hash", unique=True),
        # One TC kimlik no → one employee, same rationale as the device index.
        Index("uq_users_tc_kimlik_no", "tc_kimlik_no", unique=True),
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

    # Provenance: a real kiosk QR scan vs. a director's manual gap-fill entry
    # (phone died, forgot to scan). Manual rows are additive-only — there is no
    # endpoint that edits/deletes a qr_scan row, so this column also doubles as
    # the audit trail that proves a director never touched real scan data.
    source: Mapped[AttendanceSource] = mapped_column(
        Enum(AttendanceSource, name="attendance_source"),
        default=AttendanceSource.qr_scan,
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recorded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Which physical tablet's QR code was scanned (copied from the QR token's
    # ``kiosk`` claim). NULL for manual entries and for scans made against an
    # older kiosk build that didn't yet send an id. A campus can run several
    # kiosks at once; this lets the confirmation feed show a scan only on the
    # tablet it actually happened on, instead of on every tablet at the campus.
    kiosk_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped["User"] = relationship(back_populates="logs", foreign_keys="AttendanceLog.user_id")
    recorded_by: Mapped["User | None"] = relationship(foreign_keys="AttendanceLog.recorded_by_id")

    __table_args__ = (
        Index("ix_attendance_user_time", "user_id", "scan_time"),
    )


class LeaveRecord(Base):
    """A leave/absence period (sağlık raporu, ücretli izin, …) for one staff
    member. While ``status`` is ``active`` and today's local date falls inside
    [start_date, end_date], the staff member cannot scan — ``/api/scan`` checks
    this and tells them to see their campus director.

    ``leave_type`` is free text on purpose: the requested list (medical report,
    paid/unpaid leave, marriage/paternity/maternity leave, …) is explicitly
    open-ended ("ve benzeri"), so the API never hard-codes an exhaustive enum.
    """

    __tablename__ = "leave_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    leave_type: Mapped[str] = mapped_column(String(80), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[LeaveStatus] = mapped_column(
        Enum(LeaveStatus, name="leave_status"), default=LeaveStatus.active, nullable=False
    )
    # ``created_by`` is whoever opened the record: a manager (director-created,
    # straight to ``active``) or the staff member themselves (self-request,
    # starts ``requested``). A self-request is the case where created_by is the
    # staff member — i.e. ``created_by_id == user_id``.
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The manager who approved/rejected a staff request (NULL for director-created
    # records, which are approved implicitly at creation).
    decided_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(foreign_keys="LeaveRecord.user_id")
    created_by: Mapped["User | None"] = relationship(foreign_keys="LeaveRecord.created_by_id")
    decided_by: Mapped["User | None"] = relationship(foreign_keys="LeaveRecord.decided_by_id")

    __table_args__ = (
        Index("ix_leave_user_dates", "user_id", "start_date", "end_date"),
    )


class Holiday(Base):
    """An official holiday / campus closure excluded from absence counting.

    A ``campus_id`` of ``NULL`` means the holiday applies to **all** campuses
    (national holidays — bayram, resmi tatil); a non-null value scopes it to one
    campus (a local closure). On a date covered by an applicable holiday, the
    absence reports do not expect anyone to be present, so the day is neither an
    absence nor ``unresolved``. Managers manage these: a campus director for
    their own campus, head office globally or per-campus.
    """

    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # NULL = applies to every campus; otherwise scoped to one campus.
    campus_id: Mapped[int | None] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), index=True, nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_holiday_date_campus", "date", "campus_id"),
    )


class Announcement(Base):
    """A full-screen notice/banner shown on the campus kiosk(s).

    Used for photo celebrations (özel gün tebriği), general staff notices, event
    banners (örn. milli maç), etc. A ``campus_id`` of ``NULL`` shows the notice on
    **every** campus's kiosk; a non-null value scopes it to one campus.

    An optional image *or* video is stored as bytes *in the database* —
    production has no persistent upload volume, only the Postgres ``pgdata``
    volume, so keeping the media in a row lets a notice survive
    ``docker compose up --build``. The kiosk fetches the bytes from a separate
    public endpoint so its frequent polling stays lightweight. A notice is
    visible when ``active`` is true and "now" is within ``[starts_at, ends_at]``
    — either bound may be ``NULL`` (open-ended). A notice carries at most one of
    image/video (the upload form has a single file field).
    """

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Image bytes + its MIME type (e.g. image/jpeg). Both null for a text notice.
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    image_mime: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Video bytes + its MIME type (e.g. video/mp4) — short clips only, see
    # MAX_VIDEO_BYTES in the router. Mutually exclusive with image_data.
    video_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    video_mime: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # NULL = shown on every campus kiosk; otherwise scoped to one campus.
    campus_id: Mapped[int | None] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), index=True, nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Optional schedule window (stored UTC-aware). Null start = "from now",
    # null end = "until manually removed / deactivated".
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class LocationViolation(Base):
    """A staff QR-scan attempt rejected because the phone was too far from campus.

    Recorded only when geofencing is active for the campus and the reported
    location is outside the allowed radius — the attendance IN/OUT is *not*
    written; this row is the audit trail surfaced to managers ("şu kişi okul
    konumundan uzakta QR okuma denemesi yaptı").
    """

    __tablename__ = "location_violations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    campus_id: Mapped[int | None] = mapped_column(
        ForeignKey("campuses.id", ondelete="SET NULL"), index=True, nullable=True
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    # Straight-line distance to the campus (metres) and the phone's reported GPS
    # accuracy radius (metres), kept for context when reviewing an alert.
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
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


class Department(Base):
    """A campus' academic department / school type (bölüm), e.g. "Anadolu
    Lisesi", "Fen Lisesi". Each belongs to exactly one campus and carries the
    MEB-issued license quota (``license_quota`` — ruhsat kontenjanı): the
    department may never hold more *confirmed* student registrations than this.

    Departments and their quotas are managed centrally (head office / merkez);
    a campus director may only read them.
    """

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # MEB-issued license quota (ruhsat kontenjanı): the hard ceiling on confirmed
    # registrations across all grades of this department.
    license_quota: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    targets: Mapped[list["RegistrationTarget"]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # A department name is unique within a campus (two campuses may both run
        # an "Anadolu Lisesi", but one campus never has it twice).
        Index("uq_department_campus_name", "campus_id", "name", unique=True),
    )


class RegistrationTarget(Base):
    """The registration goal (kayıt hedefi) for one department + one grade
    (9/10/11/12), split into an internal (iç kayıt) and an external (dış kayıt)
    target. Set centrally by head office (merkez)."""

    __tablename__ = "registration_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    grade: Mapped[int] = mapped_column(Integer, nullable=False)  # 9..12
    internal_target: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    external_target: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    department: Mapped["Department"] = relationship(back_populates="targets")

    __table_args__ = (
        Index("uq_target_department_grade", "department_id", "grade", unique=True),
    )


class StudentRegistration(Base):
    """One student's registration record for a campus department.

    A record counts toward the department's license quota and toward the
    internal/external target of its (department, grade) **only when** it is both
    ``registered`` (status) and ``approved`` (by a campus manager). Its kind —
    internal vs external — is derived from the arrival channel (Geliş Kanalı):
    the channel ``İç Kayıt`` is internal, every other channel is external (see
    ``app.services.is_internal_channel``).
    """

    __tablename__ = "student_registrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Denormalised campus for scoping/queries; always equals department.campus_id
    # (the router keeps them in sync).
    campus_id: Mapped[int] = mapped_column(
        ForeignKey("campuses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)  # 9..12
    section: Mapped[str | None] = mapped_column(String(20), nullable=True)  # şube, e.g. "A"
    # Geliş Kanalı (free text — open-ended): "İç Kayıt", "Tavsiye", "Reklam", …
    arrival_channel: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(RegistrationStatus, name="registration_status"),
        default=RegistrationStatus.prospective,
        nullable=False,
    )
    # Müdür / müdür yardımcısı onayı. A registration is credited to the quota and
    # the targets only when this is true AND status is ``registered``.
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    department: Mapped["Department"] = relationship()

    __table_args__ = (
        Index("ix_student_reg_dept_grade", "department_id", "grade"),
        Index("ix_student_reg_campus", "campus_id"),
    )


class PushSubscription(Base):
    """A single browser/device Web Push subscription for one staff member.

    A person may install the PWA on more than one device, so each ``endpoint``
    (the push service URL the browser hands us) is its own row. ``p256dh`` and
    ``auth`` are the browser-supplied encryption keys we need to seal a payload
    that only that device can read. Dead endpoints (the push service answers
    404/410) are pruned on the next send attempt.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship()
