"""Pydantic request/response models."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import AttendanceStatus, AttendanceType, UserRole


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    role: UserRole
    created_at: datetime


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.teacher


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
