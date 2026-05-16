from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy import func
from app.db.base import Base
import uuid


class PushSubscription(Base):
    """
    Stores a browser's Web Push subscription for a user.
    One user can have multiple subscriptions (phone + laptop).
    """
    __tablename__ = "push_subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
