from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.push_subscription import PushSubscription
import uuid

router = APIRouter(prefix="/api/push", tags=["push"])


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribeRequest(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


@router.get("/vapid-key")
def get_vapid_key():
    """Frontend fetches this to create a push subscription."""
    return {"public_key": settings.VAPID_PUBLIC_KEY}


@router.post("/subscribe")
def subscribe(
    req: SubscribeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upsert push subscription.
    If endpoint already exists, update keys (browser may rotate them).
    """
    existing = db.query(PushSubscription).filter(
        PushSubscription.endpoint == req.endpoint
    ).first()

    if existing:
        existing.p256dh = req.keys.p256dh
        existing.auth = req.keys.auth
        existing.user_id = user.id
    else:
        db.add(PushSubscription(
            id=str(uuid.uuid4()),
            user_id=user.id,
            endpoint=req.endpoint,
            p256dh=req.keys.p256dh,
            auth=req.keys.auth,
        ))

    db.commit()
    return {"success": True}


@router.delete("/unsubscribe")
def unsubscribe(
    req: SubscribeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a push subscription (user turned off notifications)."""
    db.query(PushSubscription).filter(
        PushSubscription.endpoint == req.endpoint,
        PushSubscription.user_id == user.id,
    ).delete()
    db.commit()
    return {"success": True}
