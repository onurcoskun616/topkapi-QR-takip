"""Speech-to-text for the live meeting-minutes feature (Faz 1).

Turkish transcription via faster-whisper, CPU-only. No diarization/voice
matching happens here (that's Faz 2) — this module only turns one short audio
chunk into text. The optional ``faster_whisper`` import is guarded, mirroring
``notifications.py``'s handling of the optional ``webpush`` dependency: if the
package (or its model weights) isn't available, ASR just stays disabled rather
than taking the whole backend down.
"""
import logging
import os
import tempfile

from .config import settings

logger = logging.getLogger("attendance.asr")

try:
    from faster_whisper import WhisperModel

    _ASR_LIB_OK = True
except Exception:  # pragma: no cover - only hit if the optional dep is absent
    _ASR_LIB_OK = False


def asr_available() -> bool:
    return _ASR_LIB_OK


_model = None


def _get_model():
    global _model
    if _model is None:
        _model = WhisperModel(
            settings.asr_model_size,
            device=settings.asr_device,
            compute_type=settings.asr_compute_type,
        )
    return _model


def transcribe(audio_bytes: bytes) -> str:
    """Transcribe one short audio chunk (webm/opus, wav, …) to Turkish text.

    Blocking/CPU-bound — callers should run this off the event loop (e.g. via
    ``asyncio.to_thread``). The chunk is written to a temp file only for the
    duration of the call and always removed afterwards; audio is never
    persisted (see ``MeetingTranscriptSegment`` in models.py).
    """
    if not _ASR_LIB_OK:
        raise RuntimeError("faster-whisper is not installed")

    fd, path = tempfile.mkstemp(suffix=".webm")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio_bytes)
        model = _get_model()
        segments, _info = model.transcribe(path, language=settings.asr_language)
        return " ".join(seg.text.strip() for seg in segments).strip()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
