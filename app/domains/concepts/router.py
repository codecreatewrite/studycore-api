from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.domains.concepts.service import ConceptService
from app.domains.concepts.schemas import (
    ConceptCreate, ConceptUpdate, ConceptResponse, ConceptSummary
)
from typing import List

router = APIRouter(prefix="/api/concepts", tags=["concepts"])


@router.post("", response_model=ConceptResponse, status_code=201)
def create_concept(
    data: ConceptCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ConceptService.create(db, user.id, data)


@router.get("/due", response_model=List[ConceptSummary])
def get_due_concepts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ConceptService.get_due(db, user.id)


@router.get("/course/{course_id}", response_model=List[ConceptSummary])
def list_concepts(
    course_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ConceptService.get_all(db, user.id, course_id)


@router.get("/{concept_id}", response_model=ConceptResponse)
def get_concept(
    concept_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ConceptService.get_one(db, user.id, concept_id)


@router.put("/{concept_id}", response_model=ConceptResponse)
def update_concept(
    concept_id: str,
    data: ConceptUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return ConceptService.update(db, user.id, concept_id, data)


@router.delete("/{concept_id}", status_code=204)
def delete_concept(
    concept_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ConceptService.delete(db, user.id, concept_id)
