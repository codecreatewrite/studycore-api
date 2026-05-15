"""
FSRS v5 — Free Spaced Repetition Scheduler
Pure Python implementation.
"""
import math
from dataclasses import dataclass
from typing import Optional

W = [
    0.4072, 1.1829, 3.1262, 15.4722,
    7.2102, 0.5316, 1.0651, 0.0589,
    1.5330, 0.1544, 1.0070, 1.9395,
    0.1100, 0.2900, 2.2700, 0.1500,
    2.9898, 0.5100, 0.3400,
]

DECAY = -0.5
FACTOR = 0.9 ** (1 / DECAY) - 1
REQUESTED_RETENTION = 0.9


@dataclass
class FSRSState:
    stability: float
    difficulty: float
    is_new: bool = False


@dataclass
class FSRSResult:
    stability: float
    difficulty: float
    scheduled_days: int
    retrievability: float


def _initial_stability(rating: int) -> float:
    return W[rating - 1]


def _initial_difficulty(rating: int) -> float:
    d = W[4] - math.exp(W[5] * (rating - 1)) + 1
    return min(max(d, 1.0), 10.0)


def _retrievability(elapsed_days: float, stability: float) -> float:
    return (1 + FACTOR * elapsed_days / stability) ** DECAY


def _next_interval(stability: float) -> int:
    interval = stability / FACTOR * (REQUESTED_RETENTION ** (1 / DECAY) - 1)
    return max(1, round(interval))


def _mean_reversion(a: float, b: float) -> float:
    return W[7] * a + (1 - W[7]) * b


def _next_difficulty(d: float, rating: int) -> float:
    d_prime = d - W[6] * (rating - 3)
    return min(max(_mean_reversion(W[4], d_prime), 1.0), 10.0)


def _short_term_stability(s: float, rating: int) -> float:
    return s * math.exp(W[17] * (rating - 3 + W[18]))


def _next_stability_recall(d: float, s: float, r: float, rating: int) -> float:
    hard_penalty = W[15] if rating == 2 else 1.0
    easy_bonus = W[16] if rating == 4 else 1.0
    return s * (
        math.exp(W[8])
        * (11 - d)
        * s ** (-W[9])
        * (math.exp((1 - r) * W[10]) - 1)
        * hard_penalty
        * easy_bonus
        + 1
    )


def _next_stability_forget(d: float, s: float, r: float) -> float:
    return (
        W[11]
        * d ** (-W[12])
        * ((s + 1) ** W[13] - 1)
        * math.exp((1 - r) * W[14])
    )


def calculate(
    rating: int,
    current_state: Optional[FSRSState] = None,
    elapsed_days: float = 0,
) -> FSRSResult:
    if rating < 1 or rating > 4:
        raise ValueError(f"Rating must be 1–4, got {rating}")

    if current_state is None or current_state.is_new:
        s = _initial_stability(rating)
        d = _initial_difficulty(rating)
        interval = _next_interval(s)
        return FSRSResult(
            stability=round(s, 4),
            difficulty=round(d, 4),
            scheduled_days=interval,
            retrievability=1.0,
        )

    s = current_state.stability
    d = current_state.difficulty
    r = _retrievability(elapsed_days, s)

    if rating == 1:
        new_s = _next_stability_forget(d, s, r)
        new_d = _next_difficulty(d, rating)
        interval = max(1, round(new_s))
    else:
        new_s = _next_stability_recall(d, s, r, rating)
        new_d = _next_difficulty(d, rating)
        interval = _next_interval(new_s)

    return FSRSResult(
        stability=round(new_s, 4),
        difficulty=round(new_d, 4),
        scheduled_days=interval,
        retrievability=round(r, 4),
    )


def map_ai_score_to_rating(ai_score: float, student_rating: int) -> int:
    if ai_score >= 8.5:
        ai_rating = 4
    elif ai_score >= 6.5:
        ai_rating = 3
    elif ai_score >= 4.0:
        ai_rating = 2
    else:
        ai_rating = 1

    if student_rating == 1:
        return 1

    blended = round(0.6 * student_rating + 0.4 * ai_rating)
    return max(1, min(4, blended))
