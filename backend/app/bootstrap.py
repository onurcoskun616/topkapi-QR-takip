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
    ("users", "working_days", "VARCHAR(20)"),
    ("users", "device_fp_hash", "VARCHAR(64)"),
    ("users", "tc_kimlik_no", "VARCHAR(11)"),
    ("leave_records", "decided_by_id", "INTEGER"),
    ("leave_records", "decided_at", "TIMESTAMP WITH TIME ZONE"),
    ("campuses", "latitude", "DOUBLE PRECISION"),
    ("campuses", "longitude", "DOUBLE PRECISION"),
    ("campuses", "geofence_radius_m", "INTEGER"),
    ("announcements", "video_data", "BYTEA"),
    ("announcements", "video_mime", "VARCHAR(80)"),
]

# Unique indexes introduced after ``users`` was first created: (table, column,
# index name). Each enforces a "one value → one employee" identity rule.
_UNIQUE_INDEX_MIGRATIONS: list[tuple[str, str, str]] = [
    ("users", "device_fp_hash", "uq_users_device_fp_hash"),
    ("users", "tc_kimlik_no", "uq_users_tc_kimlik_no"),
]

# Enum values added after a PostgreSQL enum type was first created. ``create_all``
# never alters an existing type, so each new ``LeaveStatus`` member needs an
# explicit ``ALTER TYPE … ADD VALUE`` on production Postgres. SQLite stores the
# enum as a VARCHAR (no native type), so fresh tables already accept the values
# and this is a no-op there.
_ENUM_VALUE_MIGRATIONS: list[tuple[str, str]] = [
    ("leave_status", "requested"),
    ("leave_status", "rejected"),
]


def _apply_column_migrations(sync_conn) -> None:
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    is_sqlite = sync_conn.dialect.name == "sqlite"
    for table, column, ddl_type in _COLUMN_MIGRATIONS:
        if table not in existing_tables:
            continue  # create_all will have built it with the column already
        columns = {col["name"] for col in inspector.get_columns(table)}
        if column in columns:
            continue
        # SQLite has no real TIMESTAMP-WITH-TZ DDL; its flexible typing accepts
        # the bare keyword and stores the value fine.
        col_type = "TIMESTAMP" if (is_sqlite and "TIMESTAMP" in ddl_type) else ddl_type
        sync_conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'))
        logger.info("Schema upgrade: added %s.%s", table, column)


def _apply_index_migrations(sync_conn) -> None:
    """Add unique indexes introduced after a table was first created.

    ``create_all`` never alters an existing table, so a uniqueness rule added to
    a model later (e.g. ``users.device_fp_hash`` → "one device, one employee")
    needs an explicit ``CREATE UNIQUE INDEX`` on databases that predate it.
    """
    inspector = inspect(sync_conn)
    for table, column, index_name in _UNIQUE_INDEX_MIGRATIONS:
        if table not in set(inspector.get_table_names()):
            continue  # create_all will have built it with the index already
        index_names = {ix["name"] for ix in inspector.get_indexes(table)}
        if index_name in index_names:
            continue

        # Safety: never crash boot if (unexpectedly) two rows already share a
        # value. The app logic prevents this, but a pre-existing duplicate
        # would make the CREATE UNIQUE INDEX fail — skip with a loud warning.
        dup = sync_conn.execute(
            text(
                f"SELECT {column} FROM {table} "
                f"WHERE {column} IS NOT NULL "
                f"GROUP BY {column} HAVING COUNT(*) > 1 LIMIT 1"
            )
        ).first()
        if dup is not None:
            logger.warning(
                "Skipping unique index on %s.%s: a duplicate value already "
                "exists. Resolve the duplicate(s) and restart.",
                table, column,
            )
            continue

        sync_conn.execute(
            text(f"CREATE UNIQUE INDEX {index_name} ON {table} ({column})")
        )
        logger.info("Schema upgrade: unique index on %s.%s", table, column)


def _apply_enum_migrations(sync_conn) -> None:
    # Only PostgreSQL has native enum types that need altering.
    if sync_conn.dialect.name != "postgresql":
        return
    for enum_name, value in _ENUM_VALUE_MIGRATIONS:
        # IF NOT EXISTS keeps this idempotent (PostgreSQL 12+). Adding a value is
        # allowed inside a transaction as long as it is not *used* in the same one.
        sync_conn.execute(
            text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'")
        )


async def ensure_schema_upgrades() -> None:
    """Add any columns/enum values introduced after a table was first created."""
    async with engine.begin() as conn:
        await conn.run_sync(_apply_column_migrations)
        await conn.run_sync(_apply_index_migrations)
        await conn.run_sync(_apply_enum_migrations)


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
