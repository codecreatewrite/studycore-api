from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class StartRecallResponse(BaseModel):
    concept_id: str
    concept_title: str
    course_title: str
    curiosity_hook: Optional[str]
    key_point_count: int
    recall_count: int


class SubmitRecallRequest(BaseModel):
    concept_id: str
    explanation: str = Field(..., min_length=1, max_length=10000)
    duration_seconds: int = Field(..., ge=5, le=3600)
    fsrs_rating: int = Field(..., ge=1, le=4)


class GapMapResponse(BaseModel):
    covered: List[str]
    missing: List[str]
    confused: List[str]
    coverage_score: float
    depth_score: float
    tip: str
    eval_question: Optional[str]


class SubmitRecallResponse(BaseModel):
    attempt_id: str
    gap_map: Optional[GapMapResponse]
    ai_available: bool
    scheduled_days: int
    next_due: datetime
    lifecycle: str
    blended_rating: int


class SubmitClosingAnswerRequest(BaseModel):
    attempt_id: str
    answer: str = Field(..., min_length=1, max_length=3000)


class SubmitClosingAnswerResponse(BaseModel):
    feedback: str
    quality: str
