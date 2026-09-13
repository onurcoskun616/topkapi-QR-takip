"""Live meeting-minutes ("toplantı tutanağı") — Faz 1.

ASR (faster-whisper, Turkish) turns short recorded audio chunks into text; the
phone app tags each chunk with whichever participant is manually selected as
"currently speaking" (no diarization/voice-matching yet — that's Faz 2), and
any transcript line can be re-tagged or edited afterward. Faz 3 (LLM
compilation, signature/PDF) is not built here either — a meeting simply ends
with a flat, read-only transcript.

Any approved staff member may create and run their own meeting; only the
creator may mutate it (start/upload/patch/end). Raw audio is never persisted —
it's transcribed and discarded immediately (see models.py for the KVKK
rationale).
"""
import asyncio
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import asr
from ..database import get_db
from ..deps import get_current_active_staff
from ..models import (
    Meeting,
    MeetingAgendaItem,
    MeetingParticipant,
    MeetingStatus,
    MeetingTranscriptSegment,
    User,
)
from ..schemas import MeetingCreate, MeetingResponse, SegmentPatch, TranscriptSegmentResponse

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

# A single chunk shouldn't run long — callers record ~6-8s clips. This just
# guards against an oversized/misbehaving upload, not against normal use.
MAX_AUDIO_BYTES = 15 * 1024 * 1024


async def _get_owned_meeting(meeting_id: int, user: User, db: AsyncSession) -> Meeting:
    # A plain `db.get()` short-circuits to the identity map (skipping the
    # eager-load options) whenever the row is already cached in this session —
    # e.g. right after `db.add()` in create_meeting. `select().options(...)`
    # always executes and applies the loader options, so use that instead.
    result = await db.execute(
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(
            selectinload(Meeting.agenda_items),
            selectinload(Meeting.participants),
            selectinload(Meeting.segments),
        )
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı.")
    if meeting.created_by_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu toplantıyı yalnızca oluşturan kişi yönetebilir.",
        )
    return meeting


def _segment_response(seg: MeetingTranscriptSegment, name_by_id: dict[int, str]) -> TranscriptSegmentResponse:
    return TranscriptSegmentResponse(
        id=seg.id,
        participant_id=seg.participant_id,
        participant_name=name_by_id.get(seg.participant_id) if seg.participant_id else None,
        text=seg.text,
        created_at=seg.created_at,
        updated_at=seg.updated_at,
    )


def _meeting_response(meeting: Meeting) -> MeetingResponse:
    name_by_id = {p.id: p.display_name for p in meeting.participants}
    return MeetingResponse(
        id=meeting.id,
        title=meeting.title,
        status=meeting.status,
        started_at=meeting.started_at,
        ended_at=meeting.ended_at,
        created_at=meeting.created_at,
        agenda_items=meeting.agenda_items,
        participants=meeting.participants,
        segments=[_segment_response(s, name_by_id) for s in meeting.segments],
    )


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: MeetingCreate,
    user: User = Depends(get_current_active_staff),
    db: AsyncSession = Depends(get_db),
):
    meeting = Meeting(title=payload.title, created_by_id=user.id)
    db.add(meeting)
    await db.flush()

    for i, title in enumerate(payload.agenda_items):
        db.add(MeetingAgendaItem(meeting_id=meeting.id, order_index=i, title=title))
    for i, name in enumerate(payload.participants):
        db.add(MeetingParticipant(meeting_id=meeting.id, order_index=i, display_name=name))

    await db.commit()
    meeting = await _get_owned_meeting(meeting.id, user, db)
    return _meeting_response(meeting)


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: int,
    user: User = Depends(get_current_active_staff),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _get_owned_meeting(meeting_id, user, db)
    return _meeting_response(meeting)


@router.post("/{meeting_id}/start", response_model=MeetingResponse)
async def start_meeting(
    meeting_id: int,
    user: User = Depends(get_current_active_staff),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _get_owned_meeting(meeting_id, user, db)
    if meeting.status != MeetingStatus.setup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Toplantı zaten başlatılmış."
        )
    meeting.status = MeetingStatus.live
    meeting.started_at = datetime.now(timezone.utc)
    await db.commit()
    meeting = await _get_owned_meeting(meeting_id, user, db)
    return _meeting_response(meeting)


@router.post("/{meeting_id}/audio-chunk", response_model=TranscriptSegmentResponse)
async def upload_audio_chunk(
    meeting_id: int,
    audio: UploadFile = File(...),
    participant_id: int | None = Form(None),
    user: User = Depends(get_current_active_staff),
    db: AsyncSession = Depends(get_db),
):
    if not asr.asr_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ASR (konuşma tanıma) motoru bu sunucuda kurulu değil.",
        )

    meeting = await _get_owned_meeting(meeting_id, user, db)
    if meeting.status != MeetingStatus.live:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Toplantı canlı kayıtta değil."
        )

    if participant_id is not None and not any(p.id == participant_id for p in meeting.participants):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Katılımcı bulunamadı.")

    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Ses parçası çok büyük."
        )

    # faster-whisper is blocking/CPU-bound — keep it off the event loop. The
    # bytes are never written anywhere but this transient temp file inside
    # asr.transcribe, which removes it immediately after.
    text = await asyncio.to_thread(asr.transcribe, audio_bytes)
    if not text:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    segment = MeetingTranscriptSegment(
        meeting_id=meeting.id, participant_id=participant_id, text=text
    )
    db.add(segment)
    await db.commit()
    await db.refresh(segment)

    name_by_id = {p.id: p.display_name for p in meeting.participants}
    return _segment_response(segment, name_by_id)


@router.get("/{meeting_id}/segments", response_model=list[TranscriptSegmentResponse])
async def list_new_segments(
    meeting_id: int,
    after_id: int = Query(0, ge=0),
    user: User = Depends(get_current_active_staff),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _get_owned_meeting(meeting_id, user, db)
    name_by_id = {p.id: p.display_name for p in meeting.participants}
    return [
        _segment_response(s, name_by_id) for s in meeting.segments if s.id > after_id
    ]


@router.patch("/{meeting_id}/segments/{segment_id}", response_model=TranscriptSegmentResponse)
async def patch_segment(
    meeting_id: int,
    segment_id: int,
    payload: SegmentPatch,
    user: User = Depends(get_current_active_staff),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _get_owned_meeting(meeting_id, user, db)
    segment = next((s for s in meeting.segments if s.id == segment_id), None)
    if segment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Satır bulunamadı.")

    if payload.clear_participant:
        segment.participant_id = None
    elif payload.participant_id is not None:
        if not any(p.id == payload.participant_id for p in meeting.participants):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Katılımcı bulunamadı.")
        segment.participant_id = payload.participant_id
    if payload.text is not None:
        segment.text = payload.text.strip()
    segment.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(segment)
    name_by_id = {p.id: p.display_name for p in meeting.participants}
    return _segment_response(segment, name_by_id)


@router.post("/{meeting_id}/end", response_model=MeetingResponse)
async def end_meeting(
    meeting_id: int,
    user: User = Depends(get_current_active_staff),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _get_owned_meeting(meeting_id, user, db)
    if meeting.status != MeetingStatus.live:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Toplantı canlı kayıtta değil."
        )
    meeting.status = MeetingStatus.ended
    meeting.ended_at = datetime.now(timezone.utc)
    await db.commit()
    meeting = await _get_owned_meeting(meeting_id, user, db)
    return _meeting_response(meeting)
