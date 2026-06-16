"""Password hashing and JWT helpers.

Two separate token domains:
  * **Auth tokens** — long-lived teacher/admin login sessions (AUTH_SECRET).
  * **QR tokens**   — short-lived kiosk codes, 15s TTL (QR_SECRET).
"""
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --------------------------------------------------------------------------- #
# Auth (login) tokens
# --------------------------------------------------------------------------- #
def create_access_token(*, user_id: int, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()
        ),
    }
    return jwt.encode(payload, settings.auth_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raises jose.JWTError on any problem (bad signature / expired / wrong type)."""
    payload = jwt.decode(
        token, settings.auth_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "access":
        raise JWTError("Invalid token type")
    return payload


# --------------------------------------------------------------------------- #
# QR (kiosk) tokens — server time (UTC) is the only authority.
# --------------------------------------------------------------------------- #
def create_qr_token() -> dict:
    """Mint a fresh short-lived QR token. Returns token + timing metadata."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=settings.qr_token_ttl_seconds)
    jti = uuid.uuid4().hex
    payload = {
        "jti": jti,
        "type": "kiosk_qr",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, settings.qr_secret, algorithm=settings.jwt_algorithm)
    return {
        "token": token,
        "jti": jti,
        "issued_at": now,
        "expires_at": exp,
        "ttl_seconds": settings.qr_token_ttl_seconds,
    }


def decode_qr_token(token: str) -> dict:
    """Validate QR token signature, type and expiry against server time.

    ``jwt.decode`` enforces ``exp`` automatically using the server clock, so an
    expired (>15s old) token raises ``ExpiredSignatureError`` (a JWTError).
    """
    payload = jwt.decode(
        token, settings.qr_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "kiosk_qr":
        raise JWTError("Invalid QR token type")
    return payload
