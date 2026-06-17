"""Application configuration loaded from environment variables.

Pydantic-settings validates and centralises every tunable value so the rest of
the codebase never reads ``os.environ`` directly.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database
    database_url: str = "postgresql+asyncpg://topkapi:topkapi@localhost:5432/topkapi_qr"

    # JWT — three independent secrets so a leak in one domain cannot mint
    # tokens in another (QR kiosk / short access / long refresh).
    auth_secret: str = "change-me-auth"
    qr_secret: str = "change-me-qr"
    refresh_secret: str = "change-me-refresh"
    jwt_algorithm: str = "HS256"
    # Short-lived access token (the PWA silently refreshes it each morning).
    access_token_expire_minutes: int = 15
    # Long-lived refresh token bound to a single device (the "1 year" rule).
    refresh_token_expire_days: int = 365

    # QR business rule: token is valid for this many seconds (the "15s rule").
    qr_token_ttl_seconds: int = 15

    # CORS
    # Kiosk (5173), admin panel (5174) and teacher PWA (5175) dev origins.
    cors_origins: str = (
        "http://localhost:5173,http://localhost:5174,http://localhost:5175"
    )

    # Day-boundary timezone for attendance toggling (storage stays UTC).
    attendance_timezone: str = "Europe/Istanbul"

    # Bootstrap admin
    bootstrap_admin_email: str | None = "admin@topkapi.k12.tr"
    bootstrap_admin_password: str | None = "ChangeThisAdminPassword123!"
    bootstrap_admin_name: str = "System Admin"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
