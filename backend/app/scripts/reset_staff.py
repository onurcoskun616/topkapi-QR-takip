"""One-time maintenance: wipe all *staff* accounts and their attendance data.

Used to clear out test registrations before the real roll-out: every staff
member (role ``staff``) plus their scan history, leave records and sessions is
removed, so the school starts from a clean slate and everyone re-registers
fresh. Manager accounts (campus directors + head office) and campuses are
**kept** untouched.

Safe by default: running it with no arguments only *previews* what would be
deleted and changes nothing. The deletion happens only when ``--confirm`` is
passed, and runs inside a single transaction (all-or-nothing).

Run inside the backend container:

    # Preview (deletes nothing):
    docker compose -f docker-compose.prod.yml --env-file .env.prod \
        exec backend python -m app.scripts.reset_staff

    # Actually delete:
    docker compose -f docker-compose.prod.yml --env-file .env.prod \
        exec backend python -m app.scripts.reset_staff --confirm
"""
import asyncio
import sys

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import AsyncSessionLocal
from ..models import AttendanceLog, LeaveRecord, Session, User, UserRole


async def _count(session: AsyncSession, stmt) -> int:
    return int((await session.execute(stmt)).scalar() or 0)


async def gather_counts(session: AsyncSession) -> dict[str, int]:
    """How many rows a reset would remove, without deleting anything."""
    staff_ids = select(User.id).where(User.role == UserRole.staff)
    return {
        "staff": await _count(
            session, select(func.count()).select_from(User).where(User.role == UserRole.staff)
        ),
        "logs": await _count(
            session,
            select(func.count())
            .select_from(AttendanceLog)
            .where(AttendanceLog.user_id.in_(staff_ids)),
        ),
        "leaves": await _count(
            session,
            select(func.count())
            .select_from(LeaveRecord)
            .where(LeaveRecord.user_id.in_(staff_ids)),
        ),
        "sessions": await _count(
            session,
            select(func.count())
            .select_from(Session)
            .where(Session.user_id.in_(staff_ids)),
        ),
    }


async def reset_staff(session: AsyncSession) -> dict[str, int]:
    """Delete every staff account and its dependent rows, in one transaction.

    Dependents are removed explicitly in FK-dependency order so the wipe is
    correct even if the live database's foreign keys were not created with
    ``ON DELETE CASCADE``. Managers and campuses are never touched.
    """
    counts = await gather_counts(session)

    # Subquery reused for each child table: the ids of all staff accounts.
    staff_ids = select(User.id).where(User.role == UserRole.staff)

    await session.execute(delete(Session).where(Session.user_id.in_(staff_ids)))
    await session.execute(delete(AttendanceLog).where(AttendanceLog.user_id.in_(staff_ids)))
    await session.execute(delete(LeaveRecord).where(LeaveRecord.user_id.in_(staff_ids)))
    await session.execute(delete(User).where(User.role == UserRole.staff))
    await session.commit()
    return counts


def _print_preview(counts: dict[str, int]) -> None:
    print("Silinecekler (ÖNİZLEME — hiçbir şey silinmedi):")
    print(f"  • Personel hesabı     : {counts['staff']}")
    print(f"  • Giriş/çıkış kaydı    : {counts['logs']}")
    print(f"  • İzin/rapor kaydı     : {counts['leaves']}")
    print(f"  • Oturum (cihaz)       : {counts['sessions']}")
    print("\nMüdür ve genel merkez hesapları ile kampüsler KORUNUR.")
    print("Gerçekten silmek için komutu '--confirm' ekleyerek tekrar çalıştırın.")


def _print_done(counts: dict[str, int]) -> None:
    print("Sıfırlama tamamlandı. Silinen kayıtlar:")
    print(f"  • Personel hesabı     : {counts['staff']}")
    print(f"  • Giriş/çıkış kaydı    : {counts['logs']}")
    print(f"  • İzin/rapor kaydı     : {counts['leaves']}")
    print(f"  • Oturum (cihaz)       : {counts['sessions']}")
    print("\nMüdür/genel merkez hesapları ve kampüsler korundu.")
    print("Personel artık uygulamadan yeniden kayıt olabilir.")


async def _main(confirm: bool) -> None:
    async with AsyncSessionLocal() as session:
        if not confirm:
            _print_preview(await gather_counts(session))
            return
        _print_done(await reset_staff(session))


if __name__ == "__main__":
    asyncio.run(_main(confirm="--confirm" in sys.argv[1:]))
