from sqlalchemy import Column, String, DateTime, ForeignKey, Date, Text
from sqlalchemy.orm import relationship
from sqlalchemy import func
from app.db.base import Base
import uuid


class Course(Base):
    __tablename__ = "courses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    exam_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    concepts = relationship(
        "Concept",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Concept.created_at",
    )
