from sqlalchemy import Column, String, Boolean, DateTime, func
from sqlalchemy.orm import relationship
from app.db.base import Base
import uuid


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    google_id = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    picture = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    onboarding_completed = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OAuthState(Base):
    __tablename__ = "oauth_states"
    state = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
