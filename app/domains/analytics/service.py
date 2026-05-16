from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone, timedelta
from app.models.concept import Concept, ConceptLifecycle
from app.models.course import Course
from app.models.recall_attempt import RecallAttempt


class AnalyticsService:

    @staticmethod
    def get_dashboard_stats(db: Session, user_id: str) -> dict:
        """
        Everything the analytics page needs in one query set.
        Returns: overall stats + per-course breakdown + calibration trend.
        """
        now = datetime.now(timezone.utc)

        # ── All user concepts ────────────────────────────────────
        all_concepts = db.query(Concept).filter(
            Concept.user_id == user_id
        ).all()

        total_concepts = len(all_concepts)
        if total_concepts == 0:
            return _empty_stats()

        # ── Lifecycle breakdown ──────────────────────────────────
        lifecycle_counts = {}
        for c in all_concepts:
            lifecycle_counts[c.lifecycle] = lifecycle_counts.get(c.lifecycle, 0) + 1

        mastered = lifecycle_counts.get("mastered", 0)
        mature = lifecycle_counts.get("mature", 0)
        consolidating = lifecycle_counts.get("consolidating", 0)
        learning = lifecycle_counts.get("learning", 0)
        decaying = lifecycle_counts.get("decaying", 0)
        ready = lifecycle_counts.get("ready", 0)
        draft = lifecycle_counts.get("draft", 0)

        # ── Recall attempts ──────────────────────────────────────
        all_attempts = db.query(RecallAttempt).filter(
            RecallAttempt.user_id == user_id
        ).order_by(RecallAttempt.created_at.asc()).all()

        total_recalls = len(all_attempts)

        # ── Average AI score ─────────────────────────────────────
        ai_scored = [a for a in all_attempts if a.ai_coverage_score is not None]
        avg_ai_score = (
            round(sum(a.ai_coverage_score for a in ai_scored) / len(ai_scored), 1)
            if ai_scored else None
        )

        # ── Retention rate ───────────────────────────────────────
        # % of recall attempts that scored >= 6/10 (successful recall)
        successful = [a for a in ai_scored if a.ai_coverage_score >= 6.0]
        retention_rate = (
            round((len(successful) / len(ai_scored)) * 100)
            if ai_scored else None
        )

        # ── Calibration trend ────────────────────────────────────
        # Gap between student self-rating and AI coverage score over time
        # Student rating (1-4 FSRS) scaled to 0-10, vs AI coverage score
        calibration_trend = []
        for a in all_attempts[-20:]:  # Last 20 sessions
            if a.ai_coverage_score is None or a.fsrs_rating is None:
                continue
            # Scale FSRS rating (1-4) to 0-10
            student_scaled = round(((a.fsrs_rating - 1) / 3) * 10, 1)
            gap = round(student_scaled - a.ai_coverage_score, 1)
            calibration_trend.append({
                "date": a.created_at.strftime("%b %d"),
                "student_score": student_scaled,
                "ai_score": a.ai_coverage_score,
                "gap": gap,
            })

        # Calibration summary
        if len(calibration_trend) >= 3:
            avg_gap = sum(t["gap"] for t in calibration_trend) / len(calibration_trend)
            if avg_gap >= 2.0:
                calibration_state = "overconfident"
                calibration_insight = (
                    "You tend to rate yourself higher than your explanations cover. "
                    "Trust the gap map over your gut feeling."
                )
            elif avg_gap <= -2.0:
                calibration_state = "underconfident"
                calibration_insight = (
                    "You consistently underestimate yourself. "
                    "Your explanations cover more than you think."
                )
            else:
                calibration_state = "accurate"
                calibration_insight = (
                    "Your self-assessment closely matches your actual coverage. "
                    "That's a skill most students never develop."
                )
        else:
            calibration_state = "insufficient_data"
            calibration_insight = (
                "Complete more AI-evaluated sessions to see your calibration pattern."
            )

        # ── Per-course breakdown ─────────────────────────────────
        courses = db.query(Course).filter(Course.user_id == user_id).all()
        course_stats = []

        for course in courses:
            course_concepts = [c for c in all_concepts if c.course_id == course.id]
            if not course_concepts:
                continue

            cc_total = len(course_concepts)
            cc_mastered = sum(1 for c in course_concepts if c.lifecycle == "mastered")
            cc_mature = sum(1 for c in course_concepts if c.lifecycle == "mature")
            cc_decaying = sum(1 for c in course_concepts if c.lifecycle == "decaying")
            cc_ready = sum(1 for c in course_concepts if c.lifecycle in ("ready", "learning", "consolidating"))

            # Exam readiness: weighted score per concept
            # mastered=1.0, mature=0.8, consolidating=0.5, learning=0.3, decaying=0.2, ready/draft=0.0
            weights = {
                "mastered": 1.0, "mature": 0.8, "consolidating": 0.5,
                "learning": 0.3, "decaying": 0.2, "ready": 0.0, "draft": 0.0,
            }
            weighted_sum = sum(weights.get(c.lifecycle, 0) for c in course_concepts)
            readiness_pct = round((weighted_sum / cc_total) * 100)

            # Exam date projection
            days_to_exam = None
            projected_readiness = None
            if course.exam_date:
                exam_dt = datetime.combine(course.exam_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                days_to_exam = max(0, (exam_dt - now).days)

                # Simple projection: if reviewing at current pace,
                # each day adds ~2% readiness per active concept
                active_count = cc_ready + cc_decaying
                daily_gain = min(2.0, active_count * 0.5)
                projected_readiness = min(100, round(readiness_pct + (daily_gain * days_to_exam)))

            course_stats.append({
                "course_id": course.id,
                "course_title": course.title,
                "exam_date": course.exam_date.isoformat() if course.exam_date else None,
                "days_to_exam": days_to_exam,
                "total_concepts": cc_total,
                "mastered": cc_mastered,
                "mature": cc_mature,
                "decaying": cc_decaying,
                "in_progress": cc_ready,
                "readiness_pct": readiness_pct,
                "projected_readiness": projected_readiness,
            })

        # Sort courses: those with exam dates first
        course_stats.sort(key=lambda x: (x["days_to_exam"] is None, x["days_to_exam"] or 9999))

        # ── Activity — sessions per day (last 14 days) ───────────
        fourteen_days_ago = now - timedelta(days=14)
        recent_attempts = [a for a in all_attempts if a.created_at >= fourteen_days_ago]
        activity_by_day: dict[str, int] = {}
        for a in recent_attempts:
            day = a.created_at.strftime("%b %d")
            activity_by_day[day] = activity_by_day.get(day, 0) + 1

        # Fill in zeros for missing days
        activity = []
        for i in range(14):
            day = (now - timedelta(days=13 - i)).strftime("%b %d")
            activity.append({"date": day, "sessions": activity_by_day.get(day, 0)})

        return {
            "total_concepts": total_concepts,
            "total_recalls": total_recalls,
            "avg_ai_score": avg_ai_score,
            "retention_rate": retention_rate,
            "lifecycle_breakdown": {
                "mastered": mastered,
                "mature": mature,
                "consolidating": consolidating,
                "learning": learning,
                "decaying": decaying,
                "ready": ready,
                "draft": draft,
            },
            "calibration": {
                "state": calibration_state,
                "insight": calibration_insight,
                "trend": calibration_trend,
            },
            "courses": course_stats,
            "activity": activity,
        }


def _empty_stats() -> dict:
    return {
        "total_concepts": 0,
        "total_recalls": 0,
        "avg_ai_score": None,
        "retention_rate": None,
        "lifecycle_breakdown": {
            "mastered": 0, "mature": 0, "consolidating": 0,
            "learning": 0, "decaying": 0, "ready": 0, "draft": 0,
        },
        "calibration": {
            "state": "insufficient_data",
            "insight": "Complete your first recall sessions to see analytics.",
            "trend": [],
        },
        "courses": [],
        "activity": [],
    }
