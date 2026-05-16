"""
StudyCore Notification Worker
Runs as a SEPARATE Render service (not inside the web process).
Sends daily push notifications at 8 AM Africa/Lagos time.

This is a long-running process — it never exits.
Render keeps it alive as a Background Worker service.
"""
import os
import json
import time
from datetime import datetime, date, timezone
from dotenv import load_dotenv

load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler
from pywebpush import webpush, WebPushException
from sqlalchemy.orm import Session

# Import app modules
from app.db.session import SessionLocal
from app.models.push_subscription import PushSubscription
from app.models.concept import Concept, ConceptLifecycle
from app.core.config import settings

scheduler = BlockingScheduler(timezone=settings.TIMEZONE)


def send_push(subscription: PushSubscription, title: str, body: str, url: str = "/dashboard") -> bool:
    """Send a single Web Push notification. Returns True on success."""
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth,
                },
            },
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL},
            ttl=43200,  # 12 hours — expires if device stays offline
        )
        return True
    except WebPushException as e:
        status = e.response.status_code if e.response else "unknown"
        print(f"⚠️  Push failed [{status}] for user {subscription.user_id}: {e}")
        # 410 Gone = subscription is dead, should be removed
        if e.response and e.response.status_code == 410:
            _remove_dead_subscription(subscription.endpoint)
        return False
    except Exception as e:
        print(f"⚠️  Push error for user {subscription.user_id}: {e}")
        return False


def _remove_dead_subscription(endpoint: str):
    """Remove a subscription that the browser has invalidated (410 Gone)."""
    db: Session = SessionLocal()
    try:
        db.query(PushSubscription).filter(
            PushSubscription.endpoint == endpoint
        ).delete()
        db.commit()
        print(f"🗑️  Removed dead subscription: {endpoint[-30:]}")
    finally:
        db.close()


@scheduler.scheduled_job("cron", hour=8, minute=0, id="daily_notifications")
def send_daily_notifications():
    """
    Runs at 8:00 AM Africa/Lagos every day.
    Finds users with concepts due today and sends push notifications.
    """
    print(f"🔔 Starting daily notifications — {datetime.now()}")
    db: Session = SessionLocal()

    try:
        now = datetime.now(timezone.utc)

        # Get all push subscriptions
        subscriptions = db.query(PushSubscription).all()
        print(f"   Found {len(subscriptions)} push subscriptions")

        sent = 0
        skipped = 0

        for sub in subscriptions:
            # Count concepts due for this user
            due_count = db.query(Concept).filter(
                Concept.user_id == sub.user_id,
                Concept.lifecycle.in_([
                    ConceptLifecycle.READY.value,
                    ConceptLifecycle.LEARNING.value,
                    ConceptLifecycle.CONSOLIDATING.value,
                    ConceptLifecycle.MATURE.value,
                    ConceptLifecycle.DECAYING.value,
                ]),
            ).filter(
                (Concept.lifecycle == ConceptLifecycle.READY.value) |
                (Concept.due_date <= now)
            ).count()

            if due_count == 0:
                skipped += 1
                continue

            # Personalise message based on count
            if due_count == 1:
                body = "1 concept due today. Keep your memory strong."
            elif due_count <= 5:
                body = f"{due_count} concepts due today. Your review session awaits."
            else:
                body = f"{due_count} concepts due. Don't let your memory decay."

            success = send_push(
                sub,
                title="StudyCore — Review time 🧠",
                body=body,
                url="/dashboard",
            )
            if success:
                sent += 1

        print(f"✅ Notifications done — {sent} sent, {skipped} skipped (nothing due)")

    except Exception as e:
        print(f"❌ Notification job failed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    print(f"🚀 StudyCore notification worker starting")
    print(f"   Timezone: {settings.TIMEZONE}")
    print(f"   Schedule: daily at 08:00")

    # Validate VAPID keys are set
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        print("❌ VAPID keys not set — notifications will not work")
        print("   Set VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY in environment")
    else:
        print("✅ VAPID keys loaded")

    scheduler.start()
