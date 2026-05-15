from sqlalchemy import (
    Column, String, DateTime, ForeignKey,
    Integer, Float, Text, Enum
)
from sqlalchemy.orm import relationship
from sqlalchemy import func
from app.db.base import Base
import uuid
import enum


class ConceptLifecycle(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    LEARNING = "learning"
    CONSOLIDATING = "consolidating"
    MATURE = "mature"
    MASTERED = "mastered"
    DECAYING = "decaying"


class Concept(Base):
    __tablename__ = "concepts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(String, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)

    lifecycle = Column(
        Enum(ConceptLifecycle, name="concept_lifecycle"),
        nullable=False,
        default=ConceptLifecycle.DRAFT,
        server_default=ConceptLifecycle.DRAFT.value,
    )

    fsrs_stability = Column(Float, nullable=True)
    fsrs_difficulty = Column(Float, nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    recall_count = Column(Integer, default=0, nullable=False)
    last_ai_score = Column(Float, nullable=True)
    avg_ai_score = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_recalled_at = Column(DateTime(timezone=True), nullable=True)

    course = relationship("Course", back_populates="concepts")
    key_points = relationship(
        "KeyPoint",
        back_populates="concept",
        cascade="all, delete-orphan",
        order_by="KeyPoint.order",
    )
