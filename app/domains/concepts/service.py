from sqlalchemy.orm import Session
from app.models.concept import Concept, ConceptLifecycle
from app.models.course import Course
from app.models.key_point import KeyPoint
from app.domains.concepts.schemas import ConceptCreate, ConceptUpdate
from fastapi import HTTPException
from typing import List
from datetime import datetime, timezone


class ConceptService:

    @staticmethod
    def _verify_course_ownership(db: Session, user_id: str, course_id: str) -> Course:
        course = db.query(Course).filter(
            Course.id == course_id,
            Course.user_id == user_id,
        ).first()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        return course

    @staticmethod
    def _set_key_points(db: Session, concept: Concept, key_points_data: list):
        db.query(KeyPoint).filter(KeyPoint.concept_id == concept.id).delete()
        for i, kp in enumerate(key_points_data):
            db.add(KeyPoint(
                concept_id=concept.id,
                text=kp.text.strip(),
                order=i,
                is_critical=kp.is_critical,
            ))

    @staticmethod
    def _compute_lifecycle(concept: Concept) -> ConceptLifecycle:
        if not concept.key_points:
            return ConceptLifecycle.DRAFT
        if concept.recall_count == 0:
            return ConceptLifecycle.READY
        stability = concept.fsrs_stability or 0
        if stability < 7:
            return ConceptLifecycle.LEARNING
        elif stability < 21:
            return ConceptLifecycle.CONSOLIDATING
        else:
            return ConceptLifecycle.MATURE

    @staticmethod
    def create(db: Session, user_id: str, data: ConceptCreate) -> Concept:
        ConceptService._verify_course_ownership(db, user_id, data.course_id)
        concept = Concept(
            user_id=user_id,
            course_id=data.course_id,
            title=data.title.strip(),
            description=data.description,
            lifecycle=ConceptLifecycle.DRAFT,
        )
        db.add(concept)
        db.flush()
        if data.key_points:
            ConceptService._set_key_points(db, concept, data.key_points)
            concept.lifecycle = ConceptLifecycle.READY
        db.commit()
        db.refresh(concept)
        return concept

    @staticmethod
    def get_all(db: Session, user_id: str, course_id: str) -> List[Concept]:
        ConceptService._verify_course_ownership(db, user_id, course_id)
        return (
            db.query(Concept)
            .filter(Concept.course_id == course_id, Concept.user_id == user_id)
            .order_by(Concept.created_at.desc())
            .all()
        )

    @staticmethod
    def get_one(db: Session, user_id: str, concept_id: str) -> Concept:
        concept = db.query(Concept).filter(
            Concept.id == concept_id,
            Concept.user_id == user_id,
        ).first()
        if not concept:
            raise HTTPException(status_code=404, detail="Concept not found")
        return concept

    @staticmethod
    def update(db: Session, user_id: str, concept_id: str, data: ConceptUpdate) -> Concept:
        concept = ConceptService.get_one(db, user_id, concept_id)
        if data.title is not None:
            concept.title = data.title.strip()
        if data.description is not None:
            concept.description = data.description
        if data.key_points is not None:
            ConceptService._set_key_points(db, concept, data.key_points)
        db.flush()
        db.refresh(concept)
        concept.lifecycle = ConceptService._compute_lifecycle(concept)
        db.commit()
        db.refresh(concept)
        return concept

    @staticmethod
    def delete(db: Session, user_id: str, concept_id: str) -> None:
        concept = ConceptService.get_one(db, user_id, concept_id)
        db.delete(concept)
        db.commit()
    
    @staticmethod
    def get_due(db: Session, user_id: str) -> List[Concept]:
        """
        Return all concepts due for review, sorted by urgency:
        ed1. Decaying (was stable, now slipping — highest priority)
        2. Overdue (due_date in the past — ordered by most overdue first)
        3. Due today
        4. Ready (never recalled — lowest priority, no urgency)
        """
        from sqlalchemy import case, asc, desc

        now = datetime.now(timezone.utc)

        due = db.query(Concept).filter(
            Concept.user_id == user_id,
            Concept.lifecycle.in_([
                ConceptLifecycle.READY.value,
                ConceptLifecycle.LEARNING.value,
                ConceptLifecycle.CONSOLIDATING.value,
                ConceptLifecycle.MATURE.value,
                ConceptLifecycle.DECAYING.value,
            ]),
        ).filter(
            (Concept.lifecycle == ConceptLifecycle.READY.value) |
            (Concept.due_date <= now)
        ).order_by(
            # Priority 1: Decaying always first
            case(
                (Concept.lifecycle == ConceptLifecycle.DECAYING.value, 0),
                else_=1
            ).asc(),
            # Priority 2: Most overdue first (earliest due_date),
            # READY concepts (null due_date) go last within their group
            Concept.due_date.asc().nulls_last(),
        ).all()

        return due
