"""First-run helpers: create tables and a bootstrap admin account."""
import logging

from sqlalchemy import select

from .config import settings
from .database import AsyncSessionLocal, Base, engine
from .models import User, UserRole
from .security import hash_password

logger = logging.getLogger("attendance.bootstrap")


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ensure_bootstrap_admin() -> None:
    """Create the configured admin on first boot if it does not yet exist."""
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
                role=UserRole.admin,
            )
        )
        await db.commit()
        logger.info("Bootstrap admin created: %s", email)
