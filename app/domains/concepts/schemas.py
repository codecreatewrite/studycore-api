from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from app.models.concept import ConceptLifecycle


class KeyPointCreate(BaseModel):
    text: str = Field(..., min_length=3)
    is_critical: bool = False


class KeyPointResponse(BaseModel):
    id: str
    text: str
    order: int
    is_critical: bool

    model_config = {"from_attributes": True}


class ConceptCreate(BaseModel):
    course_id: str
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    key_points: List[KeyPointCreate] = Field(default_factory=list)


class ConceptUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    key_points: Optional[List[KeyPointCreate]] = None


class ConceptResponse(BaseModel):
    id: str
    course_id: str
    title: str
    description: Optional[str]
    lifecycle: ConceptLifecycle
    recall_count: int
    last_ai_score: Optional[float]
    avg_ai_score: Optional[float]
    due_date: Optional[datetime]
    last_recalled_at: Optional[datetime]
    created_at: datetime
    key_points: List[KeyPointResponse] = []

    model_config = {"from_attributes": True}


class ConceptSummary(BaseModel):
    id: str
    course_id: str
    title: str
    lifecycle: ConceptLifecycle
    recall_count: int
    avg_ai_score: Optional[float]
    due_date: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
