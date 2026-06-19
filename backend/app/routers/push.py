"""Web Push subscription management for the staff PWA.

The PWA fetches the public key, asks the browser for permission, then posts the
resulting subscription here so the server can later notify that device (e.g.
when a leave request is approved/rejected). All endpoints behave sanely when
push is disabled server-side: the public-key endpoint just reports
``enabled: false`` and the rest 404, so the PWA can hide the toggle.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user
from ..models import PushSubscription, User
from ..notifications import application_server_key, push_available
from ..schemas import (
    PushPublicKeyResponse,
    PushSubscriptionRequest,
    PushSubscriptionResult,
)

router = APIRouter(prefix="/api/push", tags=["push"])


@router.get("/public-key", response_model=PushPublicKeyResponse)
async def get_public_key():
    """Open endpoint (the key is public): tells the PWA whether push is on and,
    if so, the VAPID public key to subscribe with."""
    if not push_available():
        return PushPublicKeyResponse(enabled=False, public_key=None)
    return PushPublicKeyResponse(enabled=True, public_key=application_server_key())


@router.post("/subscribe", response_model=PushSubscriptionResult, status_code=status.HTTP_201_CREATED)
async def subscribe(
    payload: PushSubscriptionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not push_available():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bildirimler kapalı.")

    # An endpoint is globally unique; if it already exists, rebind it to this
    # user with fresh keys (a re-subscribe after the browser rotated them).
    existing = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.user_id = user.id
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
    else:
        db.add(
            PushSubscription(
                user_id=user.id,
                endpoint=payload.endpoint,
                p256dh=payload.keys.p256dh,
                auth=payload.keys.auth,
            )
        )
    await db.commit()
    return PushSubscriptionResult(subscribed=True)


@router.post("/unsubscribe", response_model=PushSubscriptionResult)
async def unsubscribe(
    payload: PushSubscriptionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == payload.endpoint,
            PushSubscription.user_id == user.id,
        )
    )
    await db.commit()
    return PushSubscriptionResult(subscribed=False)
