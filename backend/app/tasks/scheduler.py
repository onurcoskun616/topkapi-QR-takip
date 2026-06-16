"""Nightly housekeeping job (the 23:59 cron) powered by APScheduler.

Responsibilities:
  * Auto-close anyone still "inside" (last log today is IN) by appending an OUT
    log flagged ``auto_closed_by_system`` so the next day starts clean.
  * Purge expired ``UsedQrToken`` rows (replay ledger) to keep the table small.
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import delete, func, select

from ..config import settings
from ..database import AsyncSessionLocal
from ..models import (
    AttendanceLog,
    AttendanceStatus,
    AttendanceType,
    UsedQrToken,
)
from ..services import local_day_bounds_utc

logger = logging.getLogger("attendance.scheduler")

scheduler = AsyncIOScheduler(timezone="UTC")


async def auto_close_open_attendances() -> int:
    """Append a system OUT for every user whose last log today is IN.

    Returns the number of users auto-closed.
    """
    now_utc = datetime.now(timezone.utc)
    start_utc, end_utc = local_day_bounds_utc(now_utc)

    async with AsyncSessionLocal() as db:
        # Latest scan_time per user within today.
        latest_subq = (
            select(
                AttendanceLog.user_id.label("uid"),
                func.max(AttendanceLog.scan_time).label("max_time"),
            )
            .where(
                AttendanceLog.scan_time >= start_utc,
                AttendanceLog.scan_time <= end_utc,
            )
            .group_by(AttendanceLog.user_id)
            .subquery()
        )

        # Join back to find those whose latest record is an IN (still inside).
        open_logs = await db.execute(
            select(AttendanceLog).join(
                latest_subq,
                (AttendanceLog.user_id == latest_subq.c.uid)
                & (AttendanceLog.scan_time == latest_subq.c.max_time),
            ).where(AttendanceLog.type == AttendanceType.IN)
        )

        count = 0
        for last_log in open_logs.scalars().all():
            db.add(
                AttendanceLog(
                    user_id=last_log.user_id,
                    # Close at end of the local day.
                    scan_time=end_utc,
                    type=AttendanceType.OUT,
                    status=AttendanceStatus.auto_closed_by_system,
                )
            )
            count += 1

        await db.commit()

    if count:
        logger.info("Auto-closed %d open attendance record(s).", count)
    return count


async def purge_used_qr_tokens() -> int:
    """Delete replay-ledger rows older than a small multiple of the TTL."""
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=max(settings.qr_token_ttl_seconds * 4, 60)
    )
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(UsedQrToken).where(UsedQrToken.used_at < cutoff)
        )
        await db.commit()
        return result.rowcount or 0


def start_scheduler() -> None:
    """Register jobs and start the scheduler. Idempotent-ish for app startup."""
    if scheduler.running:
        return

    tz = settings.attendance_timezone

    # Nightly reset at 23:59 local time.
    scheduler.add_job(
        auto_close_open_attendances,
        trigger=CronTrigger(hour=23, minute=59, timezone=tz),
        id="auto_close_open_attendances",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Hourly cleanup of the replay ledger.
    scheduler.add_job(
        purge_used_qr_tokens,
        trigger=CronTrigger(minute=0, timezone=tz),
        id="purge_used_qr_tokens",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.start()
    logger.info("Scheduler started (timezone=%s).", tz)


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
