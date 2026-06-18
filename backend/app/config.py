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

    # Deployment environment. "production" (the default, fail-closed) enforces
    # the security self-check at startup; set APP_ENV=development locally / in
    # tests to relax it.
    app_env: str = "production"

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

    # Login brute-force guard: lock an (email, ip) pair after this many failed
    # attempts within the rolling window, for the lockout duration.
    login_max_failures: int = 8
    login_failure_window_seconds: int = 900
    login_lockout_seconds: int = 900

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# Shipped placeholder values that must never reach a real deployment: anyone
# reading the public repo could otherwise forge head-office tokens or log in as
# the bootstrap admin.
_KNOWN_WEAK_SECRETS = {
    "change-me-auth",
    "change-me-qr",
    "change-me-refresh",
    "dev-access-secret-change-in-production",
    "dev-refresh-secret-change-in-production",
    "dev-qr-secret-change-in-production",
    "change-me-to-a-long-random-string-for-access",
    "change-me-to-a-long-random-string-for-refresh",
    "change-me-to-a-long-random-string-for-qr",
}
_DEFAULT_BOOTSTRAP_PASSWORD = "ChangeThisAdminPassword123!"


def assert_production_security(cfg: "Settings") -> None:
    """Fail closed: refuse to boot in production with insecure defaults.

    Only enforced when ``APP_ENV=production`` (the default). Catches the most
    dangerous misconfigurations — shipped placeholder JWT secrets, reused
    secrets, and the documented bootstrap admin password — turning a silent
    critical vulnerability into a loud, actionable startup error.
    """
    if cfg.app_env.strip().lower() != "production":
        return

    problems: list[str] = []
    secrets = {
        "AUTH_SECRET": cfg.auth_secret,
        "REFRESH_SECRET": cfg.refresh_secret,
        "QR_SECRET": cfg.qr_secret,
    }
    for name, value in secrets.items():
        if value in _KNOWN_WEAK_SECRETS:
            problems.append(f"{name} hâlâ varsayılan/örnek değerde — değiştirin.")
        elif len(value) < 16:
            problems.append(f"{name} çok kısa (en az 16 karakter, `openssl rand -hex 32`).")

    if len(set(secrets.values())) != len(secrets):
        problems.append("AUTH_SECRET, REFRESH_SECRET ve QR_SECRET birbirinden farklı olmalı.")

    if cfg.bootstrap_admin_password and cfg.bootstrap_admin_password == _DEFAULT_BOOTSTRAP_PASSWORD:
        problems.append("BOOTSTRAP_ADMIN_PASSWORD varsayılan değerde — güçlü bir parola belirleyin.")

    if problems:
        raise RuntimeError(
            "Güvenlik denetimi başarısız — üretim ortamı güvenli olmayan "
            "ayarlarla başlatılamaz:\n  - "
            + "\n  - ".join(problems)
            + "\n\nDüzeltmek için .env.prod içinde güçlü değerler tanımlayın "
            "(her biri için: openssl rand -hex 32) ve servisi yeniden başlatın. "
            "Yerelde denetimi gevşetmek için APP_ENV=development kullanın."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
