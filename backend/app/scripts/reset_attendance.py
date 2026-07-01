"""One-time maintenance: wipe attendance history but KEEP every account.

Used to clear test/pre-launch scans before go-live: all attendance logs
(giriş/çıkış) and location-violation alerts are removed, while staff, managers,
campuses and leave records are **kept** untouched. Combined with the go-live
tracking rule (reports never count days before a person's registration / the
configured go-live date), this gives a clean start on 1 July without deleting
anyone.

Safe by default: running it with no arguments only *previews* what would be
deleted and changes nothing. The deletion happens only when ``--confirm`` is
passed, and runs inside a single transaction (all-or-nothing).

Run inside the backend container:

    # Preview (deletes nothing):
    docker compose -f docker-compose.prod.yml --env-file .env.prod \
        exec backend python -m app.scripts.reset_attendance

    # Actually delete:
    docker compose -f docker-compose.prod.yml --env-file .env.prod \
        exec backend python -m app.scripts.reset_attendance --confirm
"""
import asyncio
import sys

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..models import AttendanceLog, LocationViolation


async def _count(session: AsyncSession, model) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar() or 0)


async def gather_counts(session: AsyncSession) -> dict[str, int]:
    """How many rows a reset would remove, without deleting anything."""
    return {
        "logs": await _count(session, AttendanceLog),
        "violations": await _count(session, LocationViolation),
    }


async def reset_attendance(session: AsyncSession) -> dict[str, int]:
    """Delete all attendance logs and location violations in one transaction.

    Accounts (staff + managers), campuses and leave records are never touched.
    """
    counts = await gather_counts(session)
    await session.execute(delete(AttendanceLog))
    await session.execute(delete(LocationViolation))
    await session.commit()
    return counts


def _print_preview(counts: dict[str, int]) -> None:
    print("Silinecekler (ÖNİZLEME — hiçbir şey silinmedi):")
    print(f"  • Giriş/çıkış kaydı    : {counts['logs']}")
    print(f"  • Konum uyarısı        : {counts['violations']}")
    print("\nPersonel, müdür, kampüs ve izin kayıtları KORUNUR.")
    print("Gerçekten silmek için komutu '--confirm' ekleyerek tekrar çalıştırın.")


def _print_done(counts: dict[str, int]) -> None:
    print("Sıfırlama tamamlandı. Silinen kayıtlar:")
    print(f"  • Giriş/çıkış kaydı    : {counts['logs']}")
    print(f"  • Konum uyarısı        : {counts['violations']}")
    print("\nHesaplar, kampüsler ve izin kayıtları korundu.")
    print("Yoklama artık herkes için go-live/kayıt tarihinden itibaren tutulur.")


async def _main(confirm: bool) -> None:
    async with AsyncSessionLocal() as session:
        if not confirm:
            _print_preview(await gather_counts(session))
            return
        _print_done(await reset_attendance(session))


if __name__ == "__main__":
    asyncio.run(_main(confirm="--confirm" in sys.argv[1:]))
