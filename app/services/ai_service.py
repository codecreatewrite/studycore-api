"""
Unified AI service — Groq only, single client, validated output.
"""
from groq import Groq
from app.core.config import settings
from typing import Optional
import json
import re

_client: Optional[Groq] = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


def _call(prompt: str, max_tokens: int = 800, temperature: float = 0.3) -> Optional[str]:
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
    if not raw:
        return None
    try:
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"⚠️  JSON parse failed: {e}\nRaw: {raw[:200]}")
        return None


def _validate_gap_map(data: dict) -> dict:
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
    rubric = "\n".join(f"- {kp}" for kp in key_points)
    prompt = f"""You are a study coach evaluating a student's recall.

CONCEPT: {concept_title}

RUBRIC:
{rubric}

STUDENT'S EXPLANATION ({duration_seconds} seconds):
{explanation or "No explanation provided."}

Evaluate coverage (0-10) and depth (0-10). Identify covered, missing, confused points.
Give one actionable tip and a closing question targeting the biggest gap.

Respond ONLY with valid JSON:
{{
  "covered": [],
  "missing": [],
  "confused": [],
  "coverage_score": 7.0,
  "depth_score": 6.0,
  "tip": "...",
  "eval_question": "... or null"
}}"""
    raw = _call(prompt, max_tokens=600)
    data = _parse_json(raw)
    if not data:
        return None
    try:
        return _validate_gap_map(data)
    except (TypeError, ValueError):
        return None


def evaluate_closing_answer(
    concept_title: str,
    question: str,
    answer: str,
    key_points: list[str],
) -> Optional[dict]:
    rubric = "\n".join(f"- {kp}" for kp in key_points)
    prompt = f"""CONCEPT: {concept_title}
KEY POINTS:
{rubric}
QUESTION: {question}
STUDENT'S ANSWER: {answer or "No answer."}
Give brief feedback (2-3 sentences) and quality: strong|partial|needs_work.
JSON only: {{"feedback": "...", "quality": "strong"}}"""
    raw = _call(prompt, max_tokens=200)
    data = _parse_json(raw)
    if not data:
        return None
    quality = data.get("quality", "partial")
    if quality not in ("strong", "partial", "needs_work"):
        quality = "partial"
    return {"feedback": str(data.get("feedback", ""))[:600], "quality": quality}


def generate_curiosity_hook(concept_title: str, key_points: list[str]) -> Optional[str]:
    rubric = "\n".join(f"- {kp}" for kp in key_points[:5])
    prompt = f"""CONCEPT: {concept_title}
KEY POINTS:
{rubric}
Write ONE short sentence (max 25 words) that is counterintuitive or surprising about this concept.
Return ONLY the sentence. No JSON."""
    raw = _call(prompt, max_tokens=60, temperature=0.7)
    if not raw:
        return None
    return raw.strip().strip('"').strip("'")[:300]
