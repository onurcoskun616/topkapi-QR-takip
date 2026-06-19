"""Full-screen kiosk notices — text and/or a photo shown on the campus tablet.

Managers create notices (a celebration photo for a special day, a general staff
notice, an event banner, …); the kiosk polls the public feed in ``kiosk.py`` and
shows them full-screen with the QR code tucked into a corner.

Scope mirrors holidays:
  * **campus_director** — manages notices for *their own* campus, and sees the
    all-campus notices that also show on their kiosk (read-only).
  * **hq** — manages every notice, all-campus (``campus_id`` null) or per campus.

Images are stored as bytes in the database (production has no upload volume, so
a file on disk would be wiped on every rebuild) and served from a separate,
public endpoint so the kiosk's frequent polling stays lightweight.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_manager
from ..models import Announcement, Campus, User, UserRole
from ..schemas import (
    AnnouncementActiveUpdate,
    AnnouncementResponse,
)

router = APIRouter(prefix="/api/announcements", tags=["announcements"])

# Cap uploads so a multi-megapixel phone photo (or a long video) can't bloat a
# DB row (and the kiosk download). ~5 MB comfortably covers a good-quality
# JPEG banner; ~25 MB covers a short (15-30s), compressed celebration clip.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024


def image_path(announcement_id: int) -> str:
    """The public API path the kiosk/admin use to fetch a notice's image."""
    return f"/api/announcements/{announcement_id}/image"


def video_path(announcement_id: int) -> str:
    """The public API path the kiosk/admin use to fetch a notice's video."""
    return f"/api/announcements/{announcement_id}/video"


def is_visible(ann: Announcement, now_utc: datetime) -> bool:
    """Whether a notice should be on screen right now (active + within window)."""
    if not ann.active:
        return False
    if ann.starts_at is not None and _aware(ann.starts_at) > now_utc:
        return False
    if ann.ends_at is not None and _aware(ann.ends_at) < now_utc:
        return False
    return True


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _parse_local_dt(value: str | None) -> datetime | None:
    """Parse a ``datetime-local`` string (campus local time) into UTC-aware.

    The admin's date/time picker sends e.g. ``2026-06-20T15:30`` with no zone;
    we interpret it in the attendance timezone so "ends 15:30" means 15:30 in
    Istanbul, then store UTC.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Geçersiz tarih/saat.",
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(settings.attendance_timezone))
    return dt.astimezone(timezone.utc)


async def _campus_names(db: AsyncSession) -> dict[int, str]:
    rows = await db.execute(select(Campus.id, Campus.name))
    return {cid: name for cid, name in rows.all()}


def _to_response(ann: Announcement, names: dict[int, str]) -> AnnouncementResponse:
    return AnnouncementResponse(
        id=ann.id,
        title=ann.title,
        body=ann.body,
        has_image=ann.image_data is not None,
        image_url=image_path(ann.id) if ann.image_data is not None else None,
        has_video=ann.video_data is not None,
        video_url=video_path(ann.id) if ann.video_data is not None else None,
        campus_id=ann.campus_id,
        campus_name=names.get(ann.campus_id) if ann.campus_id else None,
        active=ann.active,
        starts_at=ann.starts_at,
        ends_at=ann.ends_at,
        created_at=ann.created_at,
    )


@router.get("", response_model=list[AnnouncementResponse])
async def list_announcements(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    campus_id: int | None = Query(None, description="hq only: filter to one campus"),
):
    stmt = select(Announcement)
    if manager.role == UserRole.campus_director:
        stmt = stmt.where(
            or_(
                Announcement.campus_id == manager.campus_id,
                Announcement.campus_id.is_(None),
            )
        )
    elif campus_id is not None:
        stmt = stmt.where(
            or_(
                Announcement.campus_id == campus_id,
                Announcement.campus_id.is_(None),
            )
        )
    stmt = stmt.order_by(Announcement.created_at.desc())

    rows = list((await db.execute(stmt)).scalars().all())
    names = await _campus_names(db)
    return [_to_response(a, names) for a in rows]


@router.post("", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
    title: str | None = Form(None),
    body: str | None = Form(None),
    campus_id: str | None = Form(None),
    starts_at: str | None = Form(None),
    ends_at: str | None = Form(None),
    media: UploadFile | None = File(None),
):
    title = (title or "").strip() or None
    body = (body or "").strip() or None

    # Read + validate the optional image/video (mutually exclusive — one file
    # field, routed by its content type).
    image_data: bytes | None = None
    image_mime: str | None = None
    video_data: bytes | None = None
    video_mime: str | None = None
    if media is not None and media.filename:
        content_type = media.content_type or ""
        if content_type.startswith("image/"):
            image_data = await media.read()
            if len(image_data) > MAX_IMAGE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Görsel en fazla 5 MB olabilir.",
                )
            image_mime = content_type
        elif content_type.startswith("video/"):
            video_data = await media.read()
            if len(video_data) > MAX_VIDEO_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Video en fazla 25 MB olabilir.",
                )
            video_mime = content_type
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Yalnızca görsel veya video dosyası yükleyebilirsiniz.",
            )

    if not title and not body and image_data is None and video_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bir başlık, metin, görsel veya video ekleyin.",
        )

    # Scope: a director is pinned to their own campus; hq picks (null = all).
    if manager.role == UserRole.campus_director:
        scope_campus_id: int | None = manager.campus_id
    else:
        scope_campus_id = (
            int(campus_id) if campus_id not in (None, "", "null") else None
        )
        if scope_campus_id is not None and await db.get(Campus, scope_campus_id) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz kampüs."
            )

    starts = _parse_local_dt(starts_at)
    ends = _parse_local_dt(ends_at)
    if starts and ends and ends < starts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bitiş, başlangıçtan önce olamaz.",
        )

    ann = Announcement(
        title=title,
        body=body,
        image_data=image_data,
        image_mime=image_mime,
        video_data=video_data,
        video_mime=video_mime,
        campus_id=scope_campus_id,
        active=True,
        starts_at=starts,
        ends_at=ends,
        created_by_id=manager.id,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    names = await _campus_names(db)
    return _to_response(ann, names)


async def _load_scoped(
    announcement_id: int, manager: User, db: AsyncSession
) -> Announcement:
    ann = await db.get(Announcement, announcement_id)
    if ann is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Duyuru bulunamadı."
        )
    # A director may only touch their own campus' notices, never an all-campus one.
    if manager.role == UserRole.campus_director and ann.campus_id != manager.campus_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu duyuruyu yalnızca genel merkez yönetebilir.",
        )
    return ann


@router.patch("/{announcement_id}", response_model=AnnouncementResponse)
async def update_active(
    announcement_id: int,
    payload: AnnouncementActiveUpdate,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    ann = await _load_scoped(announcement_id, manager, db)
    ann.active = payload.active
    await db.commit()
    await db.refresh(ann)
    names = await _campus_names(db)
    return _to_response(ann, names)


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_announcement(
    announcement_id: int,
    manager: User = Depends(get_current_manager),
    db: AsyncSession = Depends(get_db),
):
    ann = await _load_scoped(announcement_id, manager, db)
    await db.delete(ann)
    await db.commit()


@router.get("/{announcement_id}/image")
async def get_announcement_image(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Public: the kiosk (which has no auth) fetches the notice's image here."""
    ann = await db.get(Announcement, announcement_id)
    if ann is None or ann.image_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Görsel bulunamadı."
        )
    return Response(
        content=ann.image_data,
        media_type=ann.image_mime or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{announcement_id}/video")
async def get_announcement_video(
    announcement_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public: the kiosk fetches the notice's video here.

    Honours a ``Range`` request header (single range only) and replies
    ``206 Partial Content`` when present — some browsers (notably Safari/iOS)
    refuse to play ``<video>`` at all unless the server supports ranged
    requests, even for a short clip that easily fits in one response.
    """
    ann = await db.get(Announcement, announcement_id)
    if ann is None or ann.video_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video bulunamadı."
        )
    data = ann.video_data
    size = len(data)
    media_type = ann.video_mime or "video/mp4"

    range_header = request.headers.get("range")
    if range_header:
        try:
            range_spec = range_header.strip().removeprefix("bytes=")
            start_s, _, end_s = range_spec.partition("-")
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else size - 1
        except ValueError:
            start, end = 0, size - 1
        end = min(end, size - 1)
        if start >= size or start > end:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={"Content-Range": f"bytes */{size}"},
            )
        chunk = data[start : end + 1]
        return Response(
            content=chunk,
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=media_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=86400",
            },
        )

    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=86400",
        },
    )
