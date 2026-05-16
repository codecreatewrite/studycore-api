"""
Unified AI service — Groq only, single client, validated output.

All AI calls go through this module. No other file touches Groq directly.

Design principles:
  - Every function returns a typed result or None (never raises to caller)
  - All JSON parsing is wrapped with validation
  - Groq failures degrade gracefully — recall session still saves
  - Prompts are in this file, not scattered across routers
"""

from groq import Groq
from app.core.config import settings
from typing import Optional
import json
import re

_client: Optional[Groq] = None


def _get_client() -> Groq:
    """Lazy singleton — only instantiated when first needed."""
    global _client
    if _client is None:
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


def _call(prompt: str, max_tokens: int = 800, temperature: float = 0.3) -> Optional[str]:
    """
    Single Groq call wrapper. Returns raw text or None on any failure.
    All callers handle None gracefully.
    """
    try:
        response = _get_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️  Groq call failed: {e}")
        return None


def _parse_json(raw: Optional[str]) -> Optional[dict]:
    """
    Parse JSON from Groq response.
    Handles markdown code fences the model sometimes adds.
    Returns None if parsing fails — caller degrades gracefully.
    """
    if not raw:
        return None
    try:
        # Strip ```json ... ``` fences if present
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"⚠️  JSON parse failed: {e}\nRaw: {raw[:200]}")
        return None


def _validate_gap_map(data: dict) -> dict:
    """Ensure gap map has the expected keys with correct types."""
    return {
        "covered": [str(x) for x in data.get("covered", [])],
        "missing": [str(x) for x in data.get("missing", [])],
        "confused": [str(x) for x in data.get("confused", [])],
        "coverage_score": max(0.0, min(10.0, float(data.get("coverage_score", 0)))),
        "depth_score": max(0.0, min(10.0, float(data.get("depth_score", 0)))),
        "tip": str(data.get("tip", ""))[:500],
        "eval_question": data.get("eval_question") or None,
    }


def analyze_recall(
    concept_title: str,
    key_points: list[str],
    explanation: str,
    duration_seconds: int,
) -> Optional[dict]:
    """
    Core AI evaluation: compare student's explanation against key points rubric.

    Returns validated gap map or None if AI fails.

    Gap map schema:
    {
        "covered": ["key point the student addressed"],
        "missing": ["key point not mentioned"],
        "confused": ["concept the student got wrong or confused"],
        "coverage_score": 7.5,   # 0–10, how much of the rubric was covered
        "depth_score": 6.0,      # 0–10, quality of mechanistic explanation
        "tip": "One actionable sentence for next session.",
        "eval_question": "Question targeting biggest gap, to answer right now."
    }
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points)

    prompt = f"""You are a study coach evaluating a student's recall of a concept.

CONCEPT: {concept_title}

RUBRIC — what a complete explanation must cover:
{rubric}

STUDENT'S EXPLANATION ({duration_seconds} seconds):
{explanation or "The student submitted without writing an explanation."}

Evaluate the explanation against the rubric. Be honest and specific.

COVERAGE SCORE (0–10): How much of the rubric did they address?
  10 = every point covered accurately
  7  = most points, minor gaps
  5  = about half the rubric covered
  3  = only surface-level, major gaps
  0  = nothing meaningful

DEPTH SCORE (0–10): Did they explain mechanisms, not just labels?
  10 = clear causal reasoning throughout ("X causes Y because Z")
  5  = some mechanism, mostly labels
  0  = only named terms with no explanation

EVAL QUESTION: One short question targeting the single most critical missing concept.
  - Must be answerable in 2–4 sentences if they truly understand
  - Target mechanism, not just definition
  - Set to null if nothing is missing

Respond ONLY with valid JSON, no markdown, no extra text:
{{
  "covered": ["exact rubric point they addressed"],
  "missing": ["exact rubric point they missed"],
  "confused": ["concept they got wrong or mixed up"],
  "coverage_score": 7.0,
  "depth_score": 6.0,
  "tip": "One specific actionable sentence for their next session.",
  "eval_question": "Question to answer right now, or null"
}}"""

    raw = _call(prompt, max_tokens=600)
    data = _parse_json(raw)
    if not data:
        return None

    try:
        return _validate_gap_map(data)
    except (TypeError, ValueError) as e:
        print(f"⚠️  Gap map validation failed: {e}")
        return None


def evaluate_closing_answer(
    concept_title: str,
    question: str,
    answer: str,
    key_points: list[str],
) -> Optional[dict]:
    """
    Evaluate the student's answer to the closing eval question.
    Called immediately after they submit their closing answer.

    Returns:
    {
        "feedback": "2–3 sentence response",
        "quality": "strong" | "partial" | "needs_work"
    }
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points)

    prompt = f"""You are a study coach giving immediate feedback on a student's answer.

CONCEPT: {concept_title}

KEY CONCEPTS:
{rubric}

QUESTION ASKED: {question}

STUDENT'S ANSWER: {answer or "No answer provided."}

Give direct, specific feedback in 2–3 sentences maximum.
- If correct: confirm what they got right, add one sharpening detail
- If partial: name what they got right, name the specific gap
- If wrong/blank: give the core correct answer in plain language

Do NOT give a score. Do NOT be harsh.
Frame gaps as "here's what to add" not "you got this wrong."

Respond ONLY with valid JSON:
{{"feedback": "Your 2–3 sentence feedback.", "quality": "strong|partial|needs_work"}}"""

    raw = _call(prompt, max_tokens=200)
    data = _parse_json(raw)
    if not data:
        return None

    quality = data.get("quality", "partial")
    if quality not in ("strong", "partial", "needs_work"):
        quality = "partial"

    return {
        "feedback": str(data.get("feedback", ""))[:600],
        "quality": quality,
    }


def generate_curiosity_hook(concept_title: str, key_points: list[str]) -> Optional[str]:
    """
    Generate one counterintuitive question to show BEFORE the recall session.
    Primes encoding by creating a curiosity gap.
    Returns a single sentence string or None.
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points[:5])  # Max 5 points for hook

    prompt = f"""You are a study coach priming a student before they explain a concept from memory.

CONCEPT: {concept_title}

KEY POINTS:
{rubric}

Write ONE short sentence that:
- States something counterintuitive, surprising, or paradoxical about this concept
- Creates a gap the student will want to close
- Is directly answerable by deeply understanding the concept

Maximum 25 words. Return ONLY the sentence. No JSON. No explanation."""

    raw = _call(prompt, max_tokens=60, temperature=0.7)
    if not raw:
        return None
    # Strip any quotes the model may have added
    return raw.strip().strip('"').strip("'")[:300]

def extract_concepts_from_text(
    text: str,
    course_title: str,
) -> Optional[list[str]]:
    """
    Extract candidate concept titles from raw lecture text.
    Returns a list of concept title strings, or None if AI fails.

    Deliberately extracts TITLES ONLY — not key points.
    The student writes key points themselves.
    Max 15 concepts per extraction to prevent overwhelm.
    """
    # Truncate to ~3000 words to stay within token limits
    words = text.split()
    if len(words) > 3000:
        text = " ".join(words[:3000]) + "..."

    prompt = f"""You are helping a university student identify what to study from their lecture notes.

COURSE: {course_title}

LECTURE TEXT:
{text}

Extract the key concepts a student would need to understand and be able to explain for an exam.

Rules:
- Extract CONCEPT TITLES ONLY — not definitions, not explanations
- Each title must be specific and testable (a student could be asked about it in an exam)
- Maximum 12 concepts — quality over quantity
- Prefer mechanistic concepts over pure vocabulary
- Skip vague headings like "Introduction" or "Overview"

Good examples:
- "Mechanism of action of beta-blockers"
- "Frank-Starling law of the heart"
- "Renin-angiotensin-aldosterone system"

Bad examples:
- "The heart" (too broad)
- "Important concepts" (not specific)
- "Summary" (not a concept)

Respond ONLY with valid JSON, no markdown:
{{"concepts": ["Concept title 1", "Concept title 2", "Concept title 3"]}}"""

    raw = _call(prompt, max_tokens=400, temperature=0.3)
    data = _parse_json(raw)
    if not data:
        return None

    concepts = data.get("concepts", [])
    if not isinstance(concepts, list):
        return None

    # Validate and clean
    return [str(c).strip() for c in concepts if isinstance(c, str) and c.strip()][:12]
