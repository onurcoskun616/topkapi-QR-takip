"""First-run helpers: create tables, seed campuses, and a head-office account."""
import logging

from sqlalchemy import select

from .config import settings
from .database import AsyncSessionLocal, Base, engine
from .models import Campus, User, UserRole, UserStatus
from .security import hash_password

logger = logging.getLogger("attendance.bootstrap")

# The five campuses (name, url-safe slug). Edit here to add/rename campuses.
DEFAULT_CAMPUSES: list[tuple[str, str]] = [
    ("İkitelli OSB", "ikitelli-osb"),
    ("İstanbul OSB", "istanbul-osb"),
    ("Esenyurt", "esenyurt"),
    ("Kıraç", "kirac"),
    ("Çorlu", "corlu"),
]


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ensure_campuses() -> None:
    """Insert any missing default campuses (idempotent)."""
    async with AsyncSessionLocal() as db:
        existing = {
            slug for (slug,) in (await db.execute(select(Campus.slug))).all()
        }
        created = 0
        for name, slug in DEFAULT_CAMPUSES:
            if slug not in existing:
                db.add(Campus(name=name, slug=slug))
                created += 1
        if created:
            await db.commit()
            logger.info("Seeded %d campus(es).", created)


async def ensure_bootstrap_admin() -> None:
    """Create the configured head-office (hq) account on first boot."""
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return

    email = settings.bootstrap_admin_email.lower()
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            return
        db.add(
            User(
                full_name=settings.bootstrap_admin_name,
                email=email,
                password_hash=hash_password(settings.bootstrap_admin_password),
                role=UserRole.hq,
                status=UserStatus.active,
            )
        )
        await db.commit()
        logger.info("Bootstrap head-office (hq) account created: %s", email)
