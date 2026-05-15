from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.domains.recall.service import RecallService
from app.domains.recall.schemas import (
    StartRecallResponse,
    SubmitRecallRequest, SubmitRecallResponse,
    SubmitClosingAnswerRequest, SubmitClosingAnswerResponse,
)

router = APIRouter(prefix="/api/recall", tags=["recall"])


@router.get("/start/{concept_id}", response_model=StartRecallResponse)
def start_recall(
    concept_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return RecallService.start(db, user.id, concept_id)


@router.post("/submit", response_model=SubmitRecallResponse)
def submit_recall(
    data: SubmitRecallRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return RecallService.submit(db, user.id, data)


@router.post("/closing-answer", response_model=SubmitClosingAnswerResponse)
def submit_closing_answer(
    data: SubmitClosingAnswerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return RecallService.submit_closing_answer(db, user.id, data)
