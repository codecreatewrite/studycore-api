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
import time

_client: Optional[Groq] = None


def _get_client() -> Groq:
    """Lazy singleton — only instantiated when first needed."""
    global _client
    if _client is None:
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


def _call(prompt: str, max_tokens: int = 800, temperature: float = 0.3) -> Optional[str]:
    """
    Single Groq call wrapper with one retry on transient failure.
    Returns raw text or None on any failure.
    All callers handle None gracefully.
    """
    for attempt in range(2):
        try:
            response = _get_client().chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if attempt == 0:
                print(f"⚠️  Groq call failed (attempt 1), retrying in 2s: {e}")
                time.sleep(2)
            else:
                print(f"⚠️  Groq call failed after retry: {e}")
                return None


def _parse_json(raw: Optional[str]) -> Optional[dict]:
    """
    Parse JSON from Groq response robustly.
    Handles:
      - markdown code fences (```json ... ```)
      - preamble text before the JSON block
      - trailing text after the JSON block
    Returns None if parsing fails — caller degrades gracefully.
    """
    if not raw:
        return None
    try:
        # Strategy 1: find the outermost { ... } block in the response.
        # This handles preamble text the model sometimes adds despite instructions.
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))

        # Strategy 2: fallback — strip markdown fences and parse directly
        clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
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

    Evaluates not just WHAT was mentioned but HOW it was explained.
    Automatically adapts its evaluation lens to the type of concept:
    mechanistic (pathways, pharmacology), process-based (clinical procedures,
    community health frameworks), or conceptual/applied (psychiatry, management,
    ethics). Works equally well across all nursing and health science domains.

    Returns validated gap map or None if AI fails.
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points)
    minutes = duration_seconds // 60
    seconds = duration_seconds % 60
    duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    # Scale max_tokens to rubric size so long rubrics don't get clipped
    dynamic_max_tokens = min(1400, 900 + len(key_points) * 30)

    prompt = f"""You are an expert university examiner and study coach evaluating a nursing/health science student's explanation of a concept.

CONCEPT BEING RECALLED:
{concept_title}

MARKING RUBRIC (what a complete, accurate explanation must cover):
{rubric}

STUDENT'S EXPLANATION (written in {duration_str}):
{explanation or "[Student submitted without writing an explanation]"}

---

YOUR EVALUATION TASK:

Before scoring, silently identify what TYPE of concept this is, because the standard of depth changes accordingly:

TYPE A — MECHANISTIC (biochemical pathways, drug mechanisms, physiology, pathophysiology):
  Depth requires explaining WHY/HOW at a molecular or physiological level.
  Surface: "ADH increases water reabsorption"
  Mechanistic: "ADH binds V2 receptors → Gs → adenylyl cyclase → cAMP → PKA → AQP2 insertion into apical membrane of collecting duct"
  Naming an outcome without its mechanism = surface only.

TYPE B — PROCESS/PROCEDURAL (clinical skills, assessment steps, public health frameworks, care protocols):
  Depth requires correct sequencing, accurate criteria, and rationale for each step.
  Surface: "Assess the patient"
  Deep: "Inspect for pallor and jaundice, palpate for hepatomegaly starting from the RIF, percuss to define liver span, auscultate for bowel sounds — sequence matters because palpation after auscultation avoids disturbing bowel sounds"
  Knowing WHAT to do without knowing WHY it is done that way = surface only.

TYPE C — CONCEPTUAL/APPLIED (psychiatry, mental health, management, ethics, community models, nutrition principles):
  Depth requires accurate use of concepts, correct application to scenarios, and understanding of implications.
  Surface: "Therapeutic communication is important in mental health"
  Deep: "Therapeutic communication involves active listening, empathy, and non-judgmental responses; in psychosis specifically, you avoid challenging delusions directly because confrontation increases distress and impairs the therapeutic alliance, whereas validating the emotional experience without reinforcing the delusion maintains trust"
  Naming concepts without applying them or explaining their significance = surface only.

---

ASSESS THE EXPLANATION ACROSS THESE DIMENSIONS:

1. COVERAGE — Which rubric points were actually addressed?
   A point is covered only if the student addressed it with sufficient accuracy for its concept type.
   A point is MISSING if it was not mentioned, or only mentioned as a label with no explanation.
   A point is CONFUSED if it was addressed but with an error, reversal, or significant inaccuracy.

2. ACCURACY — Were the things stated correct?
   Flag: factual errors, cause/effect reversals, wrong names/locations/criteria, confused similar concepts.
   Example errors to catch: wrong receptor type, inverted physiology, mixed-up drug classes,
   misattributed frameworks, incorrect diagnostic criteria, wrong stage/trimester/phase.

3. DEPTH — Was the explanation deep for its concept type (A/B/C as identified above)?
   Only credit depth when the student demonstrated understanding appropriate to the concept type.
   For Type A: look for causal chains, not just outcomes.
   For Type B: look for sequencing rationale, not just step listing.
   For Type C: look for applied understanding, not just concept naming.

4. LOGICAL FLOW — Does the explanation build coherently?
   Do ideas connect logically, or is it a disconnected list?
   Poor flow often reveals memorisation without integration.

5. PRECISION — Are terms used correctly and specifically?
   Vague: "it affects the body" / "there are complications" / "the nurse should respond"
   Precise: specific anatomy, specific drugs, specific criteria, specific actions with rationale.

6. SUBTLE ERRORS — Watch especially for:
   - Cause/effect reversal
   - Confusing similar conditions, drugs, or frameworks
   - Overgeneralisation ("all diuretics..." / "all psychiatric patients...")
   - Correct concept applied to wrong context or population
   - Omitting key contraindications, exceptions, or complications that examiners test

---

SCORING:

COVERAGE SCORE (0–10): How completely did they address the rubric?
  10 = Every rubric point addressed accurately
  8  = Most points covered with mostly accurate content
  6  = About half covered
  4  = Some points mentioned but mostly surface
  2  = Very little coverage, mostly labels
  0  = Blank, irrelevant, or completely incorrect

DEPTH SCORE (0–10): How deeply did they explain what they covered? (Scored for the concept type identified)
  10 = Thorough, well-reasoned explanations with applied connections throughout
  7  = Good depth with some gaps in reasoning or application
  4  = Mix of deep and surface — some mechanisms/rationale, some labels only
  1  = Almost entirely surface — labels and definitions with no reasoning

These scores are INDEPENDENT. High coverage, low depth = memorised all points but explained none.
High depth, low coverage = explained a few things brilliantly but missed most of the rubric.

ACTIONABLE TIP:
  One specific sentence. Not "review the concept." Not "well done."
  Target the single highest-value thing to add or correct.
  Format: "[Specific gap or error] — [why it matters / how it connects to the bigger picture]"

EVAL QUESTION:
  One short, specific question targeting the most critical unresolved gap.
  Must be answerable in 2–4 sentences by someone who genuinely understands.
  Should probe understanding, not recall of a definition.
  Set to null ONLY if the explanation was genuinely complete.

---

Respond ONLY with valid JSON. No preamble. No markdown. No text outside the JSON.

{{
  "covered": ["rubric point addressed with sufficient accuracy"],
  "missing": ["rubric point not addressed or named without explanation"],
  "confused": ["specific error — what they said vs what is correct"],
  "coverage_score": 7.0,
  "depth_score": 6.0,
  "tip": "Specific actionable sentence targeting the highest-value gap.",
  "eval_question": "Targeted question probing the biggest gap, or null if complete"
}}

CRITICAL RULES:
- "covered" = addressed AND sufficiently accurate for its concept type. Named without explanation = "missing".
- "confused" must describe the specific error, not just flag it. E.g. "Said loop diuretics act on the proximal tubule — they act on the thick ascending limb of the loop of Henle" not just "wrong location".
- coverage_score and depth_score must reflect independent assessments.
- If the explanation is blank or fewer than 10 words, set both scores to 0 and set eval_question to the most fundamental rubric point.
- Be honest. A score of 9/10 must be genuinely earned. Most first attempts score 4–7."""

    raw = _call(prompt, max_tokens=dynamic_max_tokens, temperature=0.2)
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
    Assesses genuine understanding appropriate to the concept type,
    not just keyword presence.
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

Assess this answer like a professor marking a short-answer question. The concept may be mechanistic (pathways, pharmacology), procedural (clinical steps, protocols), or conceptual/applied (psychiatry, management, ethics) — apply the appropriate standard.

If CORRECT and sufficiently deep: confirm exactly what they got right, then add one precision detail that sharpens their understanding further.

If PARTIALLY CORRECT: name specifically what was right, then name the exact gap or error. Give the correct content plainly.

If INCORRECT or BLANK: give the correct answer directly and concisely. Frame it as "here's what to know" not "you got this wrong."

Rules:
- Maximum 3 sentences. Every word must earn its place.
- No hollow praise ("Great attempt!", "Well done!").
- No vague feedback ("Think about the mechanism" / "Consider the context"). Be specific.
- If they named the right concept but explained it wrong, that is partial not correct.
- The goal: student reads this and immediately knows exactly what to encode.

Respond ONLY with valid JSON:
{{"feedback": "Your 2–3 sentence feedback here.", "quality": "strong|partial|needs_work"}}

Quality definitions:
- "strong" = correct and sufficiently deep for the concept type
- "partial" = right idea, wrong or missing explanation/mechanism/rationale
- "needs_work" = incorrect, confused, or blank"""

    raw = _call(prompt, max_tokens=300, temperature=0.2)
    data = _parse_json(raw)
    if not data:
        return None

    quality = data.get("quality", "partial")
    if quality not in ("strong", "partial", "needs_work"):
        quality = "partial"

    return {
        "feedback": str(data.get("feedback", ""))[:800],
        "quality": quality,
    }


def generate_curiosity_hook(concept_title: str, key_points: list[str]) -> Optional[str]:
    """
    Generate one counterintuitive, high-curiosity question before recall.
    Activates prior knowledge and creates a gap the student wants to close.
    Works across all concept types: mechanistic, procedural, and conceptual.
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points[:5])

    prompt = f"""You are priming a university nursing/health science student before they attempt to recall a concept from memory.

CONCEPT: {concept_title}

KEY POINTS:
{rubric}

Write ONE sentence that creates intellectual tension before the student begins.

It must be:
- Counterintuitive, paradoxical, or clinically surprising
- Directly answerable by deeply understanding this concept
- Specific — not generic ("did you know this is important?")
- Under 25 words
- Appropriate to the concept type — mechanistic paradox for physiology/pharmacology, clinical dilemma for procedural concepts, real-world contradiction for conceptual/management topics

Strong examples across concept types:
- "A patient can have completely normal blood pressure readings during early haemorrhagic shock — why doesn't the body reveal this immediately?"
- "Giving oxygen to a patient in sickle cell crisis can sometimes make vaso-occlusion worse — what does this tell you about the sickling mechanism?"
- "A nurse who follows every protocol perfectly can still cause serious psychological harm — which psychiatric nursing principle explains this?"
- "A community health intervention with high coverage can actually make a disease problem worse — under what condition does this happen?"
- "A patient scoring high on a depression scale may need less immediate intervention than one scoring low — when is this true and why?"

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
    explainable ideas a student would need to demonstrate understanding of
    under exam conditions, regardless of whether the course is mechanistic,
    procedural, or conceptual.

    Works across all nursing and health science course types.
    Returns a list of concept title strings (max 12), or None if AI fails.
    """
    # Truncate to ~3000 words to stay within token limits
    words = text.split()
    if len(words) > 3000:
        text = " ".join(words[:3000]) + "\n[text truncated at 3000 words]"
        print(f"⚠️  extract_concepts: text truncated from {len(words)} words to 3000")

    prompt = f"""You are an expert academic who has spent years designing university exam questions across nursing and health science disciplines. A student has given you their lecture notes and asked you to identify what they need to be able to explain deeply for their exam.

COURSE: {course_title}

LECTURE TEXT:
{text}

---

YOUR TASK:
Extract concept titles that are genuinely worth studying deeply. These titles will become prompts for active recall practice — the student will attempt to explain each one from memory.

A good concept title must meet ALL of these criteria:

1. EXPLAINABLE — a student can be asked "explain this" and produce a coherent answer that can be evaluated
2. SPECIFIC — narrow enough to explain well in 2–5 minutes; not a whole topic, not a single word
3. ASSESSABLE — there is a clear right/wrong or better/worse way to explain it
4. STANDALONE — makes sense on its own without requiring five other concepts to be explained first
5. HIGH-YIELD — the kind of thing that actually appears on exams or matters in clinical/professional practice

WHAT COUNTS AS A GOOD CONCEPT — examples across course types:

For MECHANISTIC courses (physiology, pathophysiology, pharmacology):
  ✓ "Mechanism by which loop diuretics cause hypokalaemia"
  ✓ "How insulin resistance leads to hyperglycaemia in type 2 diabetes"
  ✓ "Renin-angiotensin-aldosterone system and blood pressure regulation"
  ✓ "Why beta-blockers are contraindicated in asthma"

For PROCEDURAL/CLINICAL courses (medical-surgical, reproductive health, nutrition):
  ✓ "Steps and rationale for abdominal assessment in a post-operative patient"
  ✓ "Partograph interpretation and when to escalate care in labour"
  ✓ "Nursing management of a patient with acute severe asthma"
  ✓ "Nutritional requirements and supplementation in pregnancy"

For PROCESS/FRAMEWORK courses (community health, public health):
  ✓ "Levels of prevention and their application in communicable disease control"
  ✓ "Epidemiological triad and how breaking any link interrupts disease transmission"
  ✓ "How herd immunity works and the threshold concept"
  ✓ "Steps of the community health nursing process"

For CONCEPTUAL/APPLIED courses (psychiatry, mental health, management, ethics):
  ✓ "Principles of therapeutic communication in psychiatric nursing"
  ✓ "Biopsychosocial model of mental illness and its nursing implications"
  ✓ "Delegation in nursing: principles, criteria, and accountability"
  ✓ "How stigma affects help-seeking behaviour in mental health"
  ✓ "Conflict resolution strategies and when to use each in a nursing team"

WHAT TO EXCLUDE:
✗ Broad topics ("The cardiovascular system", "Mental health") — too wide
✗ Pure vocabulary ("Definition of homeostasis", "What is schizophrenia") — no depth to evaluate
✗ Lists as topics ("Types of diuretics", "Classifications of mental illness") — a list is not an explainable concept
✗ Contextual or historical background ("History of nursing", "Introduction to pharmacology") — not assessable
✗ Section headings ("Overview", "Summary", "Introduction") — not concepts
✗ Anything where a student cannot demonstrate genuine understanding (vs just recall a fact)

CONCEPT TITLE FORMAT:
- Noun phrase or "How/Why" construction — not a question
- Include the specific aspect being addressed (not just the topic name)
- Specific enough that two different titles could not be confused
- 5–14 words is the sweet spot

QUANTITY:
Extract between 6 and 12 concepts. Quality over quantity.
If the text only yields 4 genuinely assessable concepts, return 4 — do not pad.
Do not force mechanistic framing onto procedural or conceptual content, or vice versa.

Respond ONLY with valid JSON. No preamble. No markdown. No text outside the JSON.
{{"concepts": ["Concept title 1", "Concept title 2", "Concept title 3"]}}"""

    raw = _call(prompt, max_tokens=600, temperature=0.2)
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

