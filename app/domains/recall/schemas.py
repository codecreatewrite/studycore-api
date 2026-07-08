from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


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
    duration_seconds: int = Field(..., ge=5)
    fsrs_rating: int = Field(..., ge=1, le=4)


class GapMapResponse(BaseModel):
    # Concept classification — now declared explicitly by AI
    concept_type: str = "B"                    # A / B / C / D / E
    concept_type_label: str = "Clinical/Process"

    # Four-way classification (upgrade from three-way)
    covered: list[str]
    surface: list[str] = []    # Named but not explained — new, between covered and missing
    missing: list[str]
    confused: list[str]

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
    quality: str   # strong | partial | needs_work
