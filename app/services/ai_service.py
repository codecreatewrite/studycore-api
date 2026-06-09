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
    Deep evaluation of a student's recall explanation.

    Evaluates not just WHAT was mentioned but HOW it was explained:
    - Mechanistic accuracy (not just label coverage)
    - Logical flow and coherence
    - Precision of language
    - Identification of subtle errors and half-truths
    - Depth of causal reasoning

    Returns validated gap map or None if AI fails.
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points)
    minutes = duration_seconds // 60
    seconds = duration_seconds % 60
    duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    prompt = f"""You are an expert examiner and study coach evaluating a university student's explanation of a concept. Your job is to assess like a strict but fair academic — the way a professor would mark a short-answer exam question.

CONCEPT BEING RECALLED:
{concept_title}

MARKING RUBRIC (what a complete, accurate explanation must include):
{rubric}

STUDENT'S EXPLANATION (written in {duration_str}):
{explanation or "[Student submitted without writing an explanation]"}

---

YOUR EVALUATION TASK:

Assess the explanation with the rigour of an academic examiner. Do not just check if keywords appear — assess whether the student demonstrated genuine understanding. A student who writes "vasopressin causes water retention" has named the outcome but shown no understanding of mechanism. A student who writes "vasopressin binds V2 receptors, activating adenylyl cyclase via Gs, raising cAMP, which activates PKA and phosphorylates aquaporin-2, causing it to insert into the apical membrane of the collecting duct" has demonstrated mechanistic understanding.

WHAT TO ASSESS:

1. COVERAGE — Which rubric points were addressed (even partially)?
   List each rubric point and whether the student addressed it.

2. ACCURACY — Were the things they said correct?
   Identify any factual errors, confused concepts, or mixed-up mechanisms.
   Even partial coverage with an error counts as "confused", not "covered".

3. MECHANISTIC DEPTH — Did they explain WHY/HOW, or just WHAT?
   Surface: "ADH increases water reabsorption"
   Mechanistic: "ADH binds V2 → Gs → adenylyl cyclase → cAMP → PKA → AQP2 insertion"
   Only mechanistic explanations earn full coverage credit.

4. LOGICAL FLOW — Does the explanation build coherently?
   Does one idea follow logically from the next, or is it a disconnected list of facts?
   Poor flow suggests memorisation without integration.

5. PRECISION — Are terms used correctly and specifically?
   Vague: "it affects the cells"
   Precise: "it acts on principal cells of the collecting duct"
   Imprecision is a gap even if the general idea is present.

6. SUBTLE ERRORS — Watch for:
   - Cause/effect reversal ("low sodium causes ADH release" vs "high osmolarity causes ADH release")
   - Incorrect receptor types, enzyme names, or anatomical locations
   - Confusing similar mechanisms (e.g. ADH vs aldosterone actions)
   - Overgeneralisation ("all diuretics block sodium" — false)
   - Stating effects without triggers or vice versa

SCORING:

COVERAGE SCORE (0–10):
  10 = Every rubric point addressed with mechanistic accuracy
  8  = Most points covered with mostly accurate mechanisms
  6  = About half covered, some mechanistic gaps
  4  = Surface coverage, few mechanisms explained
  2  = Only labels mentioned, no mechanisms
  0  = Blank or completely incorrect

DEPTH SCORE (0–10):
  10 = Thorough causal chains throughout, clinical/applied connections made
  7  = Good mechanistic reasoning with some gaps
  4  = Mix of mechanisms and surface labels
  1  = Mostly labels and definitions only

ACTIONABLE TIP:
  One specific sentence. Not general encouragement.
  Target the single highest-value thing to add next time.
  Format: "[Missing concept] — [why it matters / how it connects]"
  Example: "Add the cAMP-PKA pathway — this is the mechanism that actually moves AQP2 to the membrane, which is what examiners test."

EVAL QUESTION:
  One short, specific question targeting the most critical unresolved gap.
  Must be answerable in 2–4 sentences by someone who truly understands.
  Should probe mechanism, not definition.
  Set to null only if the explanation was genuinely complete.

---

Respond ONLY with valid JSON. No markdown. No explanation outside the JSON.

{{
  "covered": ["rubric point addressed with sufficient accuracy"],
  "missing": ["rubric point not addressed or only named without explanation"],
  "confused": ["specific error — what they said vs what is correct"],
  "coverage_score": 7.0,
  "depth_score": 6.0,
  "tip": "Specific actionable sentence targeting the highest-value gap.",
  "eval_question": "Mechanistic question targeting biggest gap, or null if complete"
}}

CRITICAL RULES:
- "covered" = addressed AND mechanistically accurate. Naming without mechanism = "missing".
- "confused" must describe the specific error, not just flag it. E.g. "Said ADH acts on proximal tubule — it acts on collecting duct" not just "wrong location".
- coverage_score and depth_score must be independent assessments. High coverage with low depth is valid (memorised all points, explained none mechanistically).
- If explanation is blank or less than 10 words, set both scores to 0 and eval_question to the most fundamental rubric point.
- Be honest. A score of 9/10 must be genuinely earned. Most first attempts should score 4–7."""

    raw = _call(prompt, max_tokens=900, temperature=0.2)
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
    Assesses mechanistic accuracy, not just keyword presence.
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points)

    prompt = f"""You are an expert examiner giving immediate feedback on a student's answer to a targeted question. This answer was written right after a recall session — the student's memory is still active.

CONCEPT: {concept_title}

KEY CONCEPTS:
{rubric}

QUESTION ASKED:
{question}

STUDENT'S ANSWER:
{answer or "[No answer provided]"}

---

Assess this answer like a professor marking a short-answer question.

If CORRECT and mechanistic: confirm exactly what they got right, add one precision detail that sharpens their understanding further.

If PARTIALLY CORRECT: name specifically what was right, then name the exact gap or error. Give the correct mechanism in plain language.

If INCORRECT or BLANK: give the correct answer directly and concisely. Frame it as "here's what to know" not "you got this wrong."

Rules:
- Maximum 3 sentences. Every word must earn its place.
- No hollow praise ("Great attempt!", "Well done!").
- No vague feedback ("Think about the mechanism"). Be specific.
- If they named the right concept but got the mechanism wrong, that is partial not correct.
- The goal: student reads this and immediately knows exactly what to encode.

Respond ONLY with valid JSON:
{{"feedback": "Your 2–3 sentence feedback here.", "quality": "strong|partial|needs_work"}}"""

    raw = _call(prompt, max_tokens=250, temperature=0.2)
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
    Generate one counterintuitive, high-curiosity question before recall.
    Activates prior knowledge and creates a gap the student wants to close.
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points[:5])

    prompt = f"""You are priming a university student before they attempt to recall a concept from memory.

CONCEPT: {concept_title}

KEY POINTS:
{rubric}

Write ONE sentence that creates intellectual tension before the student begins.

It must be:
- Counterintuitive, paradoxical, or clinically surprising
- Directly answerable by deeply understanding this concept
- Specific — not generic ("did you know this is important?")
- Under 25 words

Strong examples:
- "A patient can have completely normal blood pressure readings during early haemorrhagic shock — why doesn't the body reveal this immediately?"
- "Giving oxygen to a patient in sickle cell crisis can sometimes make vaso-occlusion worse — what does this tell you about the sickling mechanism?"
- "The same hormone that saves you from dehydration is implicated in causing dangerous hyponatraemia — how?"

Respond with ONLY the single sentence. No JSON. No quotes. No explanation."""

    raw = _call(prompt, max_tokens=80, temperature=0.7)
    if not raw:
        return None
    return raw.strip().strip('"').strip("'")[:350]

def extract_concepts_from_text(
    text: str,
    course_title: str,
) -> Optional[list[str]]:
    """
    Extract high-quality, assessable concept titles from lecture text.

    The goal is not to summarise the text — it is to identify the discrete,
    mechanistic ideas a student would need to explain under exam conditions.

    Returns a list of concept title strings (max 12), or None if AI fails.
    """
    # Truncate to ~3000 words to stay within token limits
    words = text.split()
    if len(words) > 3000:
        text = " ".join(words[:3000]) + "\n[text truncated]"

    prompt = f"""You are an expert academic who has spent years designing university exam questions. A student has given you their lecture notes and asked you to identify what they need to be able to explain deeply for their exam.

COURSE: {course_title}

LECTURE TEXT:
{text}

---

YOUR TASK:
Extract concept titles that meet ALL of the following criteria:

CRITERIA FOR A GOOD CONCEPT TITLE:
1. SPECIFIC — narrow enough that a student could explain it in 2–5 minutes
2. MECHANISTIC — about a process, mechanism, pathway, or causal relationship — not just a name or category
3. ASSESSABLE — an examiner could ask "explain X" and evaluate the answer against clear criteria
4. STANDALONE — the concept makes sense on its own without needing five other concepts explained first
5. HIGH-YIELD — the kind of thing that actually appears on exams, not background context

WHAT TO EXTRACT:
- Mechanisms of action ("Mechanism of action of beta-blockers on heart rate")
- Physiological processes ("Starling forces governing capillary fluid exchange")
- Pathophysiology ("How insulin resistance leads to type 2 diabetes")
- Clinical reasoning ("Why ACE inhibitors cause hyperkalaemia")
- Regulatory pathways ("Renin-angiotensin-aldosterone system regulation")
- Disease mechanisms ("Pathophysiology of acute respiratory distress syndrome")

WHAT NOT TO EXTRACT:
- Pure vocabulary ("Definition of homeostasis") — too shallow, no mechanism to assess
- Broad topics ("The cardiovascular system") — too wide, not a single explainable concept
- Historical/contextual facts ("Discovery of insulin in 1921") — not mechanistic
- Lists ("Types of diuretics") — a list is not an explainable concept
- Section headings ("Introduction", "Overview", "Summary") — not concepts
- Anything the student cannot be asked to "explain the mechanism of"

CONCEPT TITLE FORMAT:
- Start with a noun phrase, not a question
- Include the mechanism/process in the title where possible
- Be specific about what aspect is being addressed
- 5–12 words is ideal

GOOD TITLE EXAMPLES:
✓ "Mechanism of tubuloglomerular feedback in autoregulation of GFR"
✓ "How aldosterone increases sodium reabsorption in the collecting duct"
✓ "Pathophysiology of acute tubular necrosis following ischaemia"
✓ "Why loop diuretics cause hypokalaemia"
✓ "Compensatory mechanisms in hypovolaemic shock"

BAD TITLE EXAMPLES:
✗ "The kidney" — too broad
✗ "Diuretics" — category not mechanism
✗ "Sodium" — not a concept
✗ "Important electrolytes and their functions" — a list
✗ "Introduction to renal physiology" — contextual heading

QUANTITY:
Extract between 6 and 12 concepts. Quality over quantity.
If the text only contains 4 genuinely assessable concepts, return 4.
Do not pad with weak concepts to reach a higher number.
If the text is too vague or shallow to yield good concepts, return fewer titles with a note.

Respond ONLY with valid JSON. No markdown. No explanation:
{{"concepts": ["Concept title 1", "Concept title 2", "Concept title 3"]}}"""

    raw = _call(prompt, max_tokens=500, temperature=0.2)
    data = _parse_json(raw)
    if not data:
        return None

    concepts = data.get("concepts", [])
    if not isinstance(concepts, list):
        return None

    # Clean, validate, deduplicate
    seen = set()
    result = []
    for c in concepts:
        if not isinstance(c, str):
            continue
        cleaned = c.strip().strip('"').strip("'")
        if len(cleaned) < 5:
            continue
        lower = cleaned.lower()
        if lower in seen:
            continue
        seen.add(lower)
        result.append(cleaned)

    return result[:12]
