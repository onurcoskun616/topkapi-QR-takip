"""Web Push (VAPID) delivery to staff PWAs.

Dormant unless VAPID keys are configured (``settings.push_enabled``). The
optional ``webpush``/``httpx`` imports are guarded so that even if the package
is somehow missing at runtime the app still boots — push just stays disabled
rather than taking the whole backend down.
"""
import base64
import logging
from io import BytesIO

from sqlalchemy import delete, select

from .config import settings
from .database import AsyncSessionLocal
from .models import PushSubscription

logger = logging.getLogger("attendance.push")

try:
    import httpx
    from webpush import WebPush, WebPushSubscription

    _PUSH_LIB_OK = True
except Exception:  # pragma: no cover - only hit if the optional dep is absent
    _PUSH_LIB_OK = False


def _pem_bytes(value: str) -> bytes:
    # .env stores each PEM on one line with newlines escaped as \n; restore them.
    return value.strip().replace("\\n", "\n").encode()


def push_available() -> bool:
    return _PUSH_LIB_OK and settings.push_enabled


def application_server_key() -> str | None:
    """The VAPID public key as the browser's ``applicationServerKey`` (the raw
    uncompressed EC point, base64url, no padding). ``None`` when push is off."""
    if not settings.vapid_public_key.strip():
        return None
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    public_key = load_pem_public_key(_pem_bytes(settings.vapid_public_key))
    raw = public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


_web_push = None


def _client():
    global _web_push
    if _web_push is None:
        _web_push = WebPush(
            private_key=BytesIO(_pem_bytes(settings.vapid_private_key)),
            public_key=BytesIO(_pem_bytes(settings.vapid_public_key)),
            subscriber=settings.vapid_subject,
        )
    return _web_push


async def send_push_to_user(db, user_id: int, *, title: str, body: str, url: str = "/") -> int:
    """Send one notification to every device the staff member subscribed with.
    Prunes endpoints the push service reports as gone (404/410). Returns the
    number of successful deliveries; a no-op (0) when push is disabled."""
    if not push_available():
        return 0

    rows = await db.execute(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    )
    subs = list(rows.scalars().all())
    if not subs:
        return 0

    web_push = _client()
    payload = {"title": title, "body": body, "url": url}
    sent = 0
    dead: list[int] = []

    async with httpx.AsyncClient(timeout=10) as client:
        for sub in subs:
            try:
                subscription = WebPushSubscription.model_validate(
                    {
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    }
                )
                message = web_push.get(message=payload, subscription=subscription)
                resp = await client.post(
                    sub.endpoint, content=message.encrypted, headers=dict(message.headers)
                )
                if resp.status_code in (404, 410):
                    dead.append(sub.id)
                elif resp.status_code >= 400:
                    logger.warning("push %s failed: %s %s", sub.id, resp.status_code, resp.text[:200])
                else:
                    sent += 1
            except Exception as exc:  # pragma: no cover - network/encoding edge cases
                logger.warning("push %s error: %s", sub.id, exc)

    if dead:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(dead)))
        await db.commit()

    return sent


async def notify_user_background(user_id: int, title: str, body: str, url: str = "/") -> None:
    """Fire-and-forget wrapper for use from FastAPI ``BackgroundTasks``: opens
    its own DB session so it never touches the (already-closed) request session,
    and never raises into the background runner."""
    if not push_available():
        return
    try:
        async with AsyncSessionLocal() as db:
            await send_push_to_user(db, user_id, title=title, body=body, url=url)
    except Exception as exc:  # pragma: no cover
        logger.warning("background push to user %s failed: %s", user_id, exc)
