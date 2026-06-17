"""First-run helpers: create tables, seed campuses, and a head-office account."""
import logging

from sqlalchemy import inspect, select, text

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


# Lightweight, idempotent "add missing column" migrations for databases created
# before a column was introduced. ``create_all`` only creates *new* tables; it
# never alters an existing one, so a column added to a model later needs this.
# Each entry: (table, column, column DDL type). ``ADD COLUMN <type>`` is valid
# on both SQLite and PostgreSQL for a nullable column with no default.
_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("users", "birth_date", "DATE"),
]


def _apply_column_migrations(sync_conn) -> None:
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    for table, column, ddl_type in _COLUMN_MIGRATIONS:
        if table not in existing_tables:
            continue  # create_all will have built it with the column already
        columns = {col["name"] for col in inspector.get_columns(table)}
        if column in columns:
            continue
        sync_conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl_type}'))
        logger.info("Schema upgrade: added %s.%s", table, column)


async def ensure_schema_upgrades() -> None:
    """Add any columns introduced after the table was first created."""
    async with engine.begin() as conn:
        await conn.run_sync(_apply_column_migrations)


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
