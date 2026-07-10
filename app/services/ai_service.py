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
    Handles markdown fences, preamble text, and trailing text.
    Returns None if parsing fails.
    """
    if not raw:
        return None
    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"⚠️  JSON parse failed: {e}\nRaw: {raw[:200]}")
        return None


def _validate_gap_map(data: dict) -> dict:
    """
    Validate and normalise gap map output.
    Now includes:
    - concept_type: the AI's declared classification (A/B/C/D)
    - surface: points mentioned but without sufficient explanation
      (distinct from missing = not mentioned at all)
    """
    return {
        "concept_type": str(data.get("concept_type", "B")),
        "concept_type_label": str(data.get("concept_type_label", "Clinical/Process")),
        "covered": [str(x) for x in data.get("covered", [])],
        "surface": [str(x) for x in data.get("surface", [])],   # NEW — named but not explained
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
    Deep, calibrated evaluation of a student's recall explanation.

    Adapts depth standard to concept type AND to nursing undergraduate level.
    Distinguishes between:
      - covered    (addressed with sufficient accuracy and explanation)
      - surface    (named or mentioned without explanation — partial credit)
      - missing    (not mentioned at all)
      - confused   (mentioned with a specific error or inaccuracy)

    Returns validated gap map or None if AI fails.
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points)
    minutes = duration_seconds // 60
    seconds = duration_seconds % 60
    duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    # Scale max_tokens to rubric complexity
    dynamic_max_tokens = min(1500, 950 + len(key_points) * 35)

    prompt = f"""You are an expert nursing/health science examiner evaluating a BSc Nursing student's explanation of a concept.

STUDENT LEVEL: BSc Nursing undergraduate
CONCEPT BEING RECALLED: {concept_title}

MARKING RUBRIC (what a complete, accurate explanation must cover):
{rubric}

STUDENT'S EXPLANATION (written in {duration_str}):
{explanation or "[Student submitted without writing an explanation]"}

---

STEP 1 — CLASSIFY THE CONCEPT TYPE

Identify which type this concept belongs to and declare it in your JSON output.
Choose the SINGLE best fit:

TYPE A — MECHANISTIC
Physiology, pathophysiology, pharmacology, biochemistry.
These concepts explain how/why something happens at a physiological or organ-system level.

CRITICAL NURSING CALIBRATION FOR TYPE A:
Depth for a BSc Nursing student means clinically relevant pathophysiological reasoning —
not intracellular signalling cascades.
"ADH increases water reabsorption in the collecting duct, concentrating urine" = DEEP for nursing.
"ADH → V2 receptor → Gs → adenylyl cyclase → cAMP → PKA → AQP2 phosphorylation" = medical school level. DO NOT require this unless the rubric explicitly lists it.
The standard: can the student explain what happens, why it happens at a physiological level, and what the clinical consequence is? That is sufficient depth.

TYPE B — CLINICAL REASONING & MANAGEMENT
Medical-surgical, reproductive health, paediatrics, emergency, peri-operative, nutrition management.
These concepts require patient-centred reasoning: assessment, priorities, interventions, rationale, monitoring, complications.
Depth = correct priorities, sound rationale, awareness of complications and monitoring — not molecular mechanisms.
Example: "Nursing management of pulmonary oedema" depth is: sit upright, high-flow O2, IV furosemide, monitor urine output, watch for hypotension from diuresis — not the biochemistry of natriuretic peptides.

TYPE C — PROCEDURAL & SKILLS
Clinical procedures, assessment techniques, care protocols, infection control.
Depth = correct sequence, aseptic principles, patient safety rationale, and the "why" behind each step.
Example: inserting a urinary catheter — knowing the sequence matters, but so does why each step prevents infection.

TYPE D — INTERPRETIVE & DIAGNOSTIC
ECG rhythms, ABG analysis, partograph interpretation, lab value interpretation, imaging findings.
Depth = pattern recognition → correct classification → clinical significance → appropriate action.
Surface: "This ABG shows acidosis."
Deep: "pH 7.28, HCO3 14, pCO2 32 — metabolic acidosis with partial respiratory compensation. The low pCO2 tells me the lungs are trying to compensate, so respiratory function is intact. Most likely cause given the context is renal failure or DKA. The nurse should notify the doctor, prepare for IV bicarbonate if ordered, and monitor for cardiac arrhythmias."

TYPE E — CONCEPTUAL, THEORETICAL & APPLIED
Psychiatry, mental health, management, ethics, community health, public health frameworks, health promotion.
Depth = accurate use of theory, correct application to real scenarios, understanding of implications and exceptions.
Naming a theory without applying it, or applying it without explaining implications = surface only.

---

STEP 2 — EVALUATE THE EXPLANATION

Using the concept type you identified, assess the student's explanation:

CLASSIFY EACH RUBRIC POINT into one of four categories:

COVERED — addressed with sufficient accuracy and appropriate depth for the concept type.
A point is covered even if not perfectly complete, as long as the core idea is correct and explained.

SURFACE — mentioned or named, but without sufficient explanation for the concept type.
Example: "ADH causes water retention" for a Type A concept = surface (no mechanism at appropriate level).
Example: "Position the patient" for a Type B concept = surface (no rationale given).
Surface is NOT the same as missing. The student showed awareness but not understanding.

MISSING — not mentioned at all, or so vague it cannot be credited even at surface level.

CONFUSED — mentioned with a specific factual error, reversal, wrong location, wrong drug class,
wrong stage, or wrong direction of effect.
Always describe the specific error AND the correct version.

---

STEP 3 — CHECK FOR SUBTLE ERRORS

Even in "covered" content, watch for:
- Cause/effect reversal
- Correct concept, wrong context or population
- Confused similar drugs, conditions, or frameworks
- Overgeneralisation ("all patients with X will..." / "always do Y")
- Missing critical contraindications or exceptions that examiners test
- Incorrect staging, grading, trimester, or phase
- Anatomical imprecision (wrong side, wrong segment, wrong vessel)

If you find an error in something otherwise covered, move it to "confused" and describe the error specifically.

---

SCORING (independent of each other):

COVERAGE SCORE (0–10): How completely did they address the rubric?
  10 = Every rubric point covered or surface-covered with no significant gaps
  8  = Most points covered, minor gaps
  6  = About half covered, some surface
  4  = Several points missing, mostly surface coverage
  2  = Very little coverage
  0  = Blank or completely irrelevant

DEPTH SCORE (0–10): How well did they explain what they covered, calibrated to the concept type?
  10 = Thorough, well-reasoned explanations appropriate to the concept type throughout
  7  = Good depth with some gaps in reasoning or application
  4  = Mix — some explained well, some just named
  1  = Almost entirely surface — labels and outcomes with no reasoning

Note: A nursing student explaining a Type B concept at the correct clinical reasoning level should
score 8–10 for depth even if they mention no molecular biology. Judge depth by the standard
appropriate to the concept type, not by a universal mechanistic standard.

ACTIONABLE TIP (one sentence only):
Target the single highest-value gap or error.
Format: "[Specific gap or error] — [why it matters or how it connects]"
Not: "Review the concept." Not: "Well done." Specific and direct only.

EVAL QUESTION:
One short question targeting the most critical unresolved gap or the most important "surface" point.
Answerable in 2–4 sentences by someone who genuinely understands.
Set to null if both coverage_score ≥ 8 AND depth_score ≥ 8 (genuinely strong performance).
Otherwise always provide one.

---

Respond ONLY with valid JSON. No preamble. No markdown. No text outside the JSON.

{{
  "concept_type": "A",
  "concept_type_label": "Mechanistic",
  "covered": ["rubric point addressed with sufficient accuracy and depth"],
  "surface": ["rubric point named or partially mentioned but not sufficiently explained"],
  "missing": ["rubric point not mentioned at all"],
  "confused": ["specific error — what they said vs what is correct"],
  "coverage_score": 7.0,
  "depth_score": 6.0,
  "tip": "Specific actionable sentence targeting the highest-value gap.",
  "eval_question": "Targeted question probing biggest gap, or null if coverage≥8 AND depth≥8"
}}

ABSOLUTE RULES:
- Declare concept_type and concept_type_label. Never leave these blank.
- "covered" requires both accuracy AND appropriate explanation for the concept type.
- "surface" is for named-but-not-explained — this is NOT the same as missing.
- "confused" must name the specific error AND the correction. Never just flag "wrong."
- coverage_score and depth_score are independent. Score them separately.
- Do NOT require intracellular signalling for Type A nursing concepts unless the rubric explicitly lists it.
- If blank or under 10 words: coverage_score=0, depth_score=0, eval_question = most fundamental rubric point.
- A genuine 9–10 must be earned. Most first attempts score 4–7."""

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
    Calibrated to nursing undergraduate level — judges depth
    appropriately for the concept type, not by a universal
    molecular biology standard.
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points)

    prompt = f"""You are an expert nursing examiner giving immediate, precise feedback on a student's answer.

CONCEPT: {concept_title}

KEY CONCEPTS:
{rubric}

QUESTION ASKED: {question}

STUDENT'S ANSWER: {answer or "[No answer provided]"}

---

STUDENT LEVEL: BSc Nursing undergraduate.
The concept may be mechanistic (physiology/pharmacology at clinical level — not molecular cascades),
procedural (clinical steps with rationale), interpretive (ABG/ECG/lab pattern recognition),
or conceptual/applied (psychiatry, ethics, frameworks).
Apply the appropriate depth standard for whichever type this is.

Judge like a professor marking a short-answer exam question:

STRONG — correct and explained at appropriate depth for the concept type. Confirm what they got right, add one precision detail that sharpens understanding.

PARTIAL — right idea but explanation incomplete, mechanism missing, or rationale absent. Name what was right, name the exact gap, give the correct content plainly.

NEEDS_WORK — incorrect, confused, or blank. Give the correct answer directly. Frame as "here's what to know."

Rules:
- Maximum 3 sentences. Every word earns its place.
- No hollow praise. No vague feedback. Specific always.
- Named the right thing but explained it wrong = partial, not strong.
- Blank answer = needs_work, give the core correct answer in 2 sentences.

Respond ONLY with valid JSON:
{{"feedback": "2–3 sentence feedback.", "quality": "strong|partial|needs_work"}}"""

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
    Generate one counterintuitive question to prime recall.
    Calibrated to nursing context — clinical paradoxes, not molecular trivia.
    The hook must be answerable by deeply understanding the concept,
    not by knowing an obscure exception.
    """
    rubric = "\n".join(f"- {kp}" for kp in key_points[:5])

    prompt = f"""You are priming a BSc Nursing student before they attempt to recall a concept from memory.

CONCEPT: {concept_title}

KEY POINTS:
{rubric}

Write ONE sentence that creates intellectual tension before the student begins.

Requirements:
- Counterintuitive, paradoxical, or clinically surprising
- Directly answerable by deeply understanding this concept — not an obscure exception
- The answer must reveal one of the core mechanisms, principles, or clinical priorities in the rubric
- Specific — not generic ("did you know this is important?")
- Under 25 words
- Clinically grounded — use patient scenarios, not laboratory curiosities

Strong examples:
- "A patient can have completely normal blood pressure in early haemorrhagic shock — why doesn't the body reveal this immediately?"
- "A nurse who follows every protocol perfectly can still cause serious psychological harm — which psychiatric nursing principle explains this?"
- "Two patients with identical ABG values may need completely different immediate interventions — what determines which action comes first?"
- "A community health intervention with high coverage can worsen a disease problem — under what condition does this happen?"
- "A patient in early labour with a normal partograph can still be at high risk — what finding would make you escalate immediately?"

Respond with ONLY the single sentence. No JSON. No quotes. No explanation."""

    raw = _call(prompt, max_tokens=60, temperature=0.7)
    if not raw:
        return None
    return raw.strip().strip('"').strip("'")[:350]


def extract_concepts_from_text(
    text: str,
    course_title: str,
) -> Optional[tuple[list[str], bool]]:
    """
    Extract high-quality, assessable concept titles from lecture text.
    Returns (concepts, was_truncated) tuple.
    Limit: 4500 words. Student is informed if truncated.
    """
    words = text.split()
    was_truncated = len(words) > 4500

    if was_truncated:
        text = " ".join(words[:4500])
        print(f"⚠️  extract_concepts: truncated from {len(words)} to 4500 words")

    prompt = f"""You are an expert academic who designs university exam questions across nursing and health science disciplines. A student has given you their lecture notes. Identify what they need to be able to explain deeply for their exam.

COURSE: {course_title}

LECTURE TEXT:
{text}
{"[NOTE: Text was truncated. Only the first portion was analysed.]" if was_truncated else ""}

---

YOUR TASK:
Extract concept titles worth studying through active recall. The student will attempt to explain each one from memory — so each title must be something a student can meaningfully explain, not just name.

CRITERIA — a good concept title must be ALL of:
1. EXPLAINABLE — "explain this" produces a coherent, evaluable answer
2. SPECIFIC — explainable in 2–5 minutes; not a whole topic, not a single word
3. ASSESSABLE — clear right/wrong or better/worse
4. STANDALONE — makes sense without five other concepts being explained first
5. HIGH-YIELD — appears on exams or matters in clinical/professional practice

GOOD EXAMPLES across course types:

Mechanistic (physiology, pathophysiology, pharmacology):
  ✓ "Mechanism by which loop diuretics cause hypokalaemia"
  ✓ "How insulin resistance leads to hyperglycaemia in type 2 diabetes"
  ✓ "Why beta-blockers are contraindicated in asthma"

Clinical/Management (med-surg, reproductive health, nutrition):
  ✓ "Nursing management of a patient with acute pulmonary oedema"
  ✓ "Partograph interpretation and criteria for escalation in labour"
  ✓ "Nutritional requirements and supplementation in pregnancy"

Interpretive/Diagnostic (ABGs, ECGs, partographs, labs):
  ✓ "ABG interpretation: identifying metabolic acidosis with respiratory compensation"
  ✓ "ECG recognition of atrial fibrillation and immediate nursing priorities"

Process/Framework (community health, public health):
  ✓ "Epidemiological triad and how breaking any link interrupts disease transmission"
  ✓ "Levels of prevention and their application in communicable disease control"

Conceptual/Applied (psychiatry, mental health, ethics, management):
  ✓ "Principles of therapeutic communication in psychiatric nursing"
  ✓ "How stigma affects help-seeking behaviour in mental health"
  ✓ "Delegation in nursing: principles, criteria, and accountability"

EXCLUDE:
✗ Broad topics ("The cardiovascular system") — too wide
✗ Pure vocabulary ("Definition of homeostasis") — no depth
✗ Lists ("Types of diuretics") — a list is not an explainable concept
✗ Historical/contextual background ("History of nursing") — not assessable
✗ Section headings ("Overview", "Introduction", "Summary")
✗ Concepts where "explaining" only means reciting a fact

DEDUPLICATION:
If two titles refer to the same concept from different angles, merge them into one specific title.
Example: "Mechanism of oedema in nephrotic syndrome" + "How nephrotic syndrome causes oedema" → one concept.

FORMAT:
- Noun phrase or "How/Why/Steps" construction — not a question
- Include the specific aspect being addressed
- 5–14 words

QUANTITY: 6–12 concepts. If only 4 are genuinely assessable, return 4. Do not pad.

---

CRITICAL FORMAT REQUIREMENT:
Each concept title must be a SEPARATE string in the array.
Do NOT concatenate multiple titles into one string.
Do NOT join titles without separators.

CORRECT:
{{"concepts": ["Mechanism of antipsychotic medications in reducing positive symptoms", "Principles of therapeutic communication in psychiatric nursing", "Biopsychosocial model of mental illness and its implications for treatment"]}}

INCORRECT:
{{"concepts": ["Mechanism of antipsychotic medications in reducing positive symptomsPrinciples of therapeutic communication in psychiatric nursingBiopsychosocial model..."]}}

Respond ONLY with valid JSON. No preamble. No markdown. No text outside the JSON.
{{"concepts": ["Concept title 1", "Concept title 2", "Concept title 3"]}}"""

    raw = _call(prompt, max_tokens=600, temperature=0.2)
    data = _parse_json(raw)
    if not data:
        return None

    concepts = data.get("concepts", [])
    if not isinstance(concepts, list):
        return None

    # ── Concatenation fix ────────────────────────────────────────────────
    # The AI occasionally returns all concepts joined into one long string
    # instead of separate array items. Detect and split these cases.
    # Heuristic: if any single item is longer than 120 chars, it's likely
    # multiple concepts concatenated without separators.
    expanded = []
    for c in concepts:
        if not isinstance(c, str):
            continue
        c = c.strip()
        if len(c) > 120:
            # Try to split on capital letters that start new concept titles
            # Pattern: split before an uppercase word that follows a lowercase word
            # e.g. "...therapyMechanism..." → "...therapy" + "Mechanism..."
            parts = re.split(r'(?<=[a-z])(?=[A-Z])', c)
            # Also try splitting on common phrase starters
            if len(parts) <= 1:
                parts = re.split(
                    r'(?:(?<=\w)\s+(?=(?:Mechanism|Principles|How|Why|Role|'
                    r'Steps|Nursing|Management|Pathophysiology|Causes|Effects|'
                    r'Types|Classification|Criteria|Assessment|Treatment|'
                    r'Diagnosis|Complications|Prevention|Rehabilitation|'
                    r'Pharmacology|Clinical|Biopsychosocial|De-escalation|'
                    r'Electroconvulsive|Neuroleptic|Schizophrenia|CBT|DSM)))',
                    c
                )
            expanded.extend([p.strip() for p in parts if p.strip()])
        else:
            expanded.append(c)

    # ── Standard clean + deduplicate ─────────────────────────────────────
    seen = set()
    result = []
    for c in expanded:
        cleaned = c.strip().strip('"').strip("'")
        if len(cleaned) < 5:
            continue
        lower = cleaned.lower()
        if lower in seen:
            continue
        seen.add(lower)
        result.append(cleaned)

    return result[:12], was_truncated
