from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy import func
from app.db.base import Base
import uuid


class KeyPoint(Base):
    __tablename__ = "key_points"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    concept_id = Column(
        String,
        ForeignKey("concepts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    text = Column(Text, nullable=False)
    order = Column(Integer, nullable=False, default=0)
    is_critical = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    concept = relationship("Concept", back_populates="key_points")
