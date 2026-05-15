from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional


class CourseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    exam_date: Optional[date] = None


class CourseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    exam_date: Optional[date] = None


class CourseResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    exam_date: Optional[date]
    concept_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}
