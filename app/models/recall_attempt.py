from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy import func
from app.db.base import Base
import uuid


class RecallAttempt(Base):
    __tablename__ = "recall_attempts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    concept_id = Column(String, ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    explanation = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    fsrs_rating = Column(Integer, nullable=True)

    ai_coverage_score = Column(Float, nullable=True)
    ai_depth_score = Column(Float, nullable=True)
    ai_gap_map = Column(JSON, nullable=True)
    ai_tip = Column(Text, nullable=True)
    ai_eval_question = Column(Text, nullable=True)
    ai_eval_answer = Column(Text, nullable=True)
    ai_eval_feedback = Column(Text, nullable=True)

    fsrs_stability_after = Column(Float, nullable=True)
    fsrs_difficulty_after = Column(Float, nullable=True)
    scheduled_days = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    concept = relationship("Concept")
