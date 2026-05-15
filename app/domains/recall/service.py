from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

from app.models.concept import Concept, ConceptLifecycle
from app.models.recall_attempt import RecallAttempt
from app.models.key_point import KeyPoint
from app.services import fsrs as FSRS
from app.services.ai_service import analyze_recall, evaluate_closing_answer, generate_curiosity_hook
from app.domains.recall.schemas import (
    SubmitRecallRequest, SubmitRecallResponse,
    StartRecallResponse, GapMapResponse,
    SubmitClosingAnswerRequest, SubmitClosingAnswerResponse,
)


class RecallService:

    @staticmethod
    def _get_concept(db: Session, user_id: str, concept_id: str) -> Concept:
        concept = db.query(Concept).filter(
            Concept.id == concept_id,
            Concept.user_id == user_id,
        ).first()
        if not concept:
            raise HTTPException(status_code=404, detail="Concept not found")
        return concept

    @staticmethod
    def _get_key_point_texts(concept: Concept) -> list[str]:
        return [kp.text for kp in sorted(concept.key_points, key=lambda x: x.order)]

    @staticmethod
    def _compute_lifecycle(stability: float, rating: int) -> ConceptLifecycle:
        if rating == 1:
            return ConceptLifecycle.DECAYING
        if stability < 7:
            return ConceptLifecycle.LEARNING
        elif stability < 21:
            return ConceptLifecycle.CONSOLIDATING
        else:
            return ConceptLifecycle.MATURE

    @staticmethod
    def start(db: Session, user_id: str, concept_id: str) -> StartRecallResponse:
        concept = RecallService._get_concept(db, user_id, concept_id)
        key_points = RecallService._get_key_point_texts(concept)

        if concept.lifecycle == ConceptLifecycle.DRAFT:
            raise HTTPException(400, detail="Add key points before recalling.")

        hook = None
        if key_points:
            hook = generate_curiosity_hook(concept.title, key_points)

        return StartRecallResponse(
            concept_id=concept.id,
            concept_title=concept.title,
            course_title=concept.course.title if concept.course else "",
            curiosity_hook=hook,
            key_point_count=len(key_points),
            recall_count=concept.recall_count,
        )

    @staticmethod
    def submit(db: Session, user_id: str, data: SubmitRecallRequest) -> SubmitRecallResponse:
        concept = RecallService._get_concept(db, user_id, data.concept_id)
        key_points = RecallService._get_key_point_texts(concept)

        # AI evaluation
        ai_result = None
        if key_points:
            ai_result = analyze_recall(
                concept_title=concept.title,
                key_points=key_points,
                explanation=data.explanation,
                duration_seconds=data.duration_seconds,
            )

        # Blend ratings
        if ai_result:
            blended_rating = FSRS.map_ai_score_to_rating(ai_result["coverage_score"], data.fsrs_rating)
        else:
            blended_rating = data.fsrs_rating

        # FSRS calculation
        current_state = None
        elapsed_days = 0.0
        if concept.fsrs_stability is not None and concept.last_recalled_at is not None:
            elapsed_days = (datetime.now(timezone.utc) - concept.last_recalled_at).total_seconds() / 86400
            current_state = FSRS.FSRSState(
                stability=concept.fsrs_stability,
                difficulty=concept.fsrs_difficulty or 5.0,
            )

        fsrs_result = FSRS.calculate(
            rating=blended_rating,
            current_state=current_state,
            elapsed_days=elapsed_days,
        )

        now = datetime.now(timezone.utc)
        next_due = now + timedelta(days=fsrs_result.scheduled_days)

        # Update concept
        concept.fsrs_stability = fsrs_result.stability
        concept.fsrs_difficulty = fsrs_result.difficulty
        concept.due_date = next_due
        concept.last_recalled_at = now
        concept.recall_count = (concept.recall_count or 0) + 1
        concept.last_ai_score = ai_result["coverage_score"] if ai_result else None
        if ai_result:
            if concept.avg_ai_score is None:
                concept.avg_ai_score = ai_result["coverage_score"]
            else:
                concept.avg_ai_score = round(0.7 * concept.avg_ai_score + 0.3 * ai_result["coverage_score"], 2)

        concept.lifecycle = RecallService._compute_lifecycle(fsrs_result.stability, blended_rating).value

        # Save attempt
        attempt = RecallAttempt(
            concept_id=concept.id,
            user_id=user_id,
            explanation=data.explanation,
            duration_seconds=data.duration_seconds,
            fsrs_rating=data.fsrs_rating,
            ai_coverage_score=ai_result["coverage_score"] if ai_result else None,
            ai_depth_score=ai_result["depth_score"] if ai_result else None,
            ai_gap_map=ai_result if ai_result else None,
            ai_tip=ai_result["tip"] if ai_result else None,
            ai_eval_question=ai_result.get("eval_question") if ai_result else None,
            fsrs_stability_after=fsrs_result.stability,
            fsrs_difficulty_after=fsrs_result.difficulty,
            scheduled_days=fsrs_result.scheduled_days,
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)

        gap_map = None
        if ai_result:
            gap_map = GapMapResponse(
                covered=ai_result["covered"],
                missing=ai_result["missing"],
                confused=ai_result["confused"],
                coverage_score=ai_result["coverage_score"],
                depth_score=ai_result["depth_score"],
                tip=ai_result["tip"],
                eval_question=ai_result.get("eval_question"),
            )

        return SubmitRecallResponse(
            attempt_id=attempt.id,
            gap_map=gap_map,
            ai_available=ai_result is not None,
            scheduled_days=fsrs_result.scheduled_days,
            next_due=next_due,
            lifecycle=concept.lifecycle,
            blended_rating=blended_rating,
        )

    @staticmethod
    def submit_closing_answer(
        db: Session,
        user_id: str,
        data: SubmitClosingAnswerRequest,
    ) -> SubmitClosingAnswerResponse:
        attempt = db.query(RecallAttempt).filter(
            RecallAttempt.id == data.attempt_id,
            RecallAttempt.user_id == user_id,
        ).first()
        if not attempt:
            raise HTTPException(404, "Recall attempt not found")
        if not attempt.ai_eval_question:
            raise HTTPException(400, "No eval question for this attempt")

        concept = db.query(Concept).filter(Concept.id == attempt.concept_id).first()
        key_points = [kp.text for kp in concept.key_points] if concept else []

        result = evaluate_closing_answer(
            concept_title=concept.title if concept else "",
            question=attempt.ai_eval_question,
            answer=data.answer,
            key_points=key_points,
        )

        attempt.ai_eval_answer = data.answer
        if result:
            attempt.ai_eval_feedback = result["feedback"]
        db.commit()

        if not result:
            return SubmitClosingAnswerResponse(
                feedback="Good attempt. Review the concept before your next session.",
                quality="partial",
            )
        return SubmitClosingAnswerResponse(
            feedback=result["feedback"],
            quality=result["quality"],
        )
