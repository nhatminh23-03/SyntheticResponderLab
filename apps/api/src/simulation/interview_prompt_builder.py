"""Build system and user prompts for synthetic depth-interview generation.

Converts a persona dict (from PersonaPreviewPersona.persona_json) into a
role-play system prompt, and formats a list of interview questions into
a user prompt requesting structured JSON responses.

Three-layer prompt structure (STAMP-inspired):
  1. Definition layer    — role + persona description + product context
  2. Inclusion/exclusion — fit-tier and awareness behavioral constraints
  3. Examples + CoT      — response style anchors, then answer questions
"""

from __future__ import annotations

from typing import Any, Optional


# ---------------------------------------------------------------------------
# Fit-tier and awareness behavioral constraints (layer 2)
# ---------------------------------------------------------------------------

_FIT_TIER_CONSTRAINTS: dict[str, str] = {
    "strong": (
        " You are actively interested in solving this problem and have been researching solutions. "
        "Include specific details, enthusiasm where warranted, and clear purchase signals."
    ),
    "soft": (
        " You recognize the problem but have real concerns — cost, space, or unclear value — that "
        "have kept you from buying. Surface genuine hesitation while staying open-minded."
    ),
    "latent": (
        " You have the underlying need but have never thought of it as something a product could solve. "
        "Show curiosity mixed with uncertainty; avoid assertive purchase intent."
    ),
    "edge": (
        " You have an adjacent use case and are curious, but you are not sure this product is really "
        "meant for someone like you. Express conditional interest with real caveats."
    ),
}

_AWARENESS_CONSTRAINTS: dict[str, str] = {
    "aware": (
        " You are familiar with products in this category and have formed opinions about what works "
        "and what does not. Reference that experience naturally."
    ),
    "unaware": (
        " You are not aware that solutions like this exist, though you may have the underlying need. "
        "React as someone encountering this category for the first time."
    ),
}

# ---------------------------------------------------------------------------
# Default interview questions
# ---------------------------------------------------------------------------

DEFAULT_QUESTIONS: list[dict[str, str]] = [
    {
        "id": "IQ1",
        "text": (
            "How do you currently use [product_category] or similar solutions? "
            "What's your relationship with them day-to-day?"
        ),
    },
    {
        "id": "IQ2",
        "text": "What unmet needs or frustrations do you have that [product_name] could address?",
    },
    {
        "id": "IQ3",
        "text": (
            "Have you considered similar products or solutions before? "
            "What happened — did you buy, and if not, why not?"
        ),
    },
    {
        "id": "IQ4",
        "text": (
            "If you could design the ideal version of [product_name] for your situation, "
            "what would it look like and how would you use it?"
        ),
    },
    {
        "id": "IQ5",
        "text": (
            "How does [product_name] fit into your work-life balance or daily routine? "
            "What would change if you had it?"
        ),
    },
    {
        "id": "IQ6",
        "text": (
            "What's your honest first reaction to [product_name] at [price_range]? "
            "What stands out — positively or negatively?"
        ),
    },
    {
        "id": "IQ7",
        "text": (
            "What would be your biggest concerns or deal-breakers? "
            "And what would need to be true for you to actually buy it?"
        ),
    },
    {
        "id": "IQ8",
        "text": "How would you discover something like this, and who would you talk to about it?",
    },
]


def resolve_questions(
    questions: list[dict[str, str]] | None,
    product: dict | None,
) -> list[dict[str, str]]:
    """Return resolved question list with product placeholders filled in."""
    base = questions if questions else DEFAULT_QUESTIONS

    product_name = ""
    product_category = ""
    price_range = ""
    if product:
        product_name = product.get("product_name") or ""
        product_category = product.get("product_type") or product.get("industry") or ""
        price_range = product.get("price_range") or ""

    product_name = product_name or "this product"
    product_category = product_category or "this type of product"
    price_range = price_range or "the listed price"

    resolved = []
    for q in base:
        text = q["text"]
        text = text.replace("[product_name]", product_name)
        text = text.replace("[product_category]", product_category)
        text = text.replace("[price_range]", price_range)
        resolved.append({"id": q["id"], "text": text})
    return resolved


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_system_prompt(
    persona: dict,
    product: Optional[dict],
    audience: Optional[dict],
) -> str:
    """Build a three-layer role-play system prompt from persona/product/audience dicts.

    Layer 1 — Definition: role + persona description + product context
    Layer 2 — Inclusion/exclusion: fit-tier and awareness behavioral constraints
    Layer 3 — Response style anchor (implicit via instructions)
    """
    # --- Layer 1: Persona description ---
    age = persona.get("age_bucket") or "unknown age"
    income = persona.get("income_bucket") or "unknown income"
    ownership = persona.get("ownership") or "unknown tenure"
    work_mode = persona.get("work_mode") or "unknown work arrangement"
    home_type = persona.get("home_type") or "unknown home type"
    segment = persona.get("segment_label") or ""
    lifestyle_tags = persona.get("lifestyle_tags") or []
    use_case = persona.get("likely_use_case") or ""
    barrier = persona.get("likely_barrier") or ""
    affordability = persona.get("affordability_pressure") or ""
    fit_tier = persona.get("fit_tier") or ""
    awareness_stage = persona.get("awareness_stage") or ""

    persona_desc = (
        f"You are a {age} year-old {ownership} living in a {home_type}. "
        f"Your household income is in the {income} range. "
        f"You work {work_mode}."
    )
    if lifestyle_tags:
        persona_desc += f" Your lifestyle includes: {', '.join(lifestyle_tags)}."
    if segment:
        persona_desc += f" You identify most with the '{segment}' customer type."
    if use_case:
        persona_desc += f" Your primary interest area is: {use_case}."
    if barrier:
        persona_desc += f" A key concern for you tends to be: {barrier}."
    if affordability and affordability != "unknown":
        persona_desc += f" Your affordability situation is: {affordability.replace('_', ' ')}."

    # --- Layer 2: Behavioral constraints ---
    constraint = ""
    if fit_tier in _FIT_TIER_CONSTRAINTS:
        constraint += _FIT_TIER_CONSTRAINTS[fit_tier]
    if awareness_stage in _AWARENESS_CONSTRAINTS:
        constraint += _AWARENESS_CONSTRAINTS[awareness_stage]

    # --- Product context ---
    product_context = ""
    if product:
        product_name = product.get("product_name") or ""
        description = product.get("product_description") or ""
        price_range = product.get("price_range") or ""
        target = product.get("target_customer") or ""
        features = product.get("key_features") or []
        visual_labels = product.get("product_image_labels") or []
        visual_objects = product.get("product_image_objects") or []
        visual_colors = product.get("product_image_colors") or []

        if any([product_name, description, features, visual_labels, visual_objects, visual_colors]):
            product_context = "\n\nPRODUCT BEING DISCUSSED:\n"
            if product_name:
                product_context += f"Name: {product_name}\n"
            if price_range:
                product_context += f"Price: {price_range}\n"
            if description:
                product_context += f"Description: {description}\n"
            if features:
                product_context += f"Key features: {', '.join(features[:5])}\n"
            if visual_labels:
                product_context += f"Visual labels: {', '.join(visual_labels[:6])}\n"
            if visual_objects:
                product_context += f"Visible objects: {', '.join(visual_objects[:6])}\n"
            if visual_colors:
                product_context += f"Dominant colors: {', '.join(visual_colors[:5])}\n"
            if target:
                product_context += f"Intended for: {target}\n"

    # --- Audience/geography context ---
    audience_context = ""
    if audience:
        notes = audience.get("notes") or ""
        state = audience.get("state") or ""
        metro = audience.get("metro") or ""
        location_parts = [p for p in [metro, state] if p]
        if location_parts:
            audience_context = f"\n\nYou are based in {', '.join(location_parts)}."
        if notes:
            audience_context += f" Additional context: {notes}"

    system_prompt = f"""\
You are role-playing as a real person participating in a qualitative depth interview.

YOUR PERSONA:
{persona_desc}{constraint}{audience_context}{product_context}

INSTRUCTIONS:
- Stay fully in character throughout the interview. Answer authentically based on your persona.
- Be specific and personal — use first-person language, share genuine opinions, hesitations, and enthusiasm where appropriate.
- Do NOT give generic marketing-speak answers. Reflect the real tensions, trade-offs, and priorities your persona would have.
- Keep each answer substantive: 3–6 sentences minimum, conversational in tone.
- When asked about the product, engage with it honestly — you may be skeptical, curious, excited, or uncertain depending on your situation.
- You will be given a JSON schema to follow. Return ONLY valid JSON — no preamble, no markdown fences."""

    return system_prompt


def build_user_prompt(questions: list[dict[str, str]]) -> str:
    """Build the user prompt listing questions and requesting JSON output."""
    question_lines = "\n".join(f'{q["id"]}: {q["text"]}' for q in questions)
    answer_keys = ", ".join(f'"{q["id"]}": "<your answer>"' for q in questions)

    return f"""\
Please answer each of the following interview questions as your persona.

INTERVIEW QUESTIONS:
{question_lines}

Return your answers as a single JSON object with exactly these keys:
{{
  {answer_keys},
  "additional_thoughts": "<anything else you want to add — optional, can be empty string>"
}}

IMPORTANT: Return ONLY the JSON object. No markdown, no commentary outside the JSON."""


def build_judge_prompt(
    questions: list[dict[str, str]],
    answers_a: dict[str, str],
    answers_b: dict[str, str],
    persona: dict,
) -> tuple[str, str]:
    """Build system + user prompts for the judge LLM grounding scorer.

    The judge evaluates whether both models produced thematically consistent
    answers across four dimensions and returns a JSON agreement object.
    """
    fit_tier = persona.get("fit_tier") or "unknown"
    segment = persona.get("segment_label") or "unknown"

    system_prompt = f"""\
You are a qualitative research analyst evaluating inter-rater reliability between two synthetic interview transcripts.

Your task: for a persona with fit_tier="{fit_tier}" and segment="{segment}", assess whether Model A and Model B \
gave thematically consistent answers across four grounding dimensions.

DIMENSIONS TO SCORE (1 = consistent, 0 = inconsistent):
- purchase_intent: Do both transcripts express the same level of purchase interest or intent? \
(Strong vs soft vs resistant — they don't need identical wording, just consistent signaling.)
- primary_objection: Do both transcripts surface the same main barrier or concern? \
(Same category of objection, not exact wording.)
- fit_tier_alignment: Do both responses behaviorally match the expected fit_tier "{fit_tier}"? \
(A "strong" persona should not sound disinterested; a "latent" persona should not give strong purchase signals.)
- use_case_specificity: Do both transcripts reference similarly concrete use cases? \
(Both vague, or both specific — not one concrete and one generic.)

Score each dimension 1 or 0. Return ONLY a JSON object with these four keys. No explanation, no markdown."""

    q_map = {q["id"]: q["text"] for q in questions}

    transcript_block = "MODEL A ANSWERS:\n"
    for qid, ans in answers_a.items():
        if qid == "additional_thoughts":
            continue
        transcript_block += f"{qid} ({q_map.get(qid, '')}): {ans}\n\n"

    transcript_block += "\nMODEL B ANSWERS:\n"
    for qid, ans in answers_b.items():
        if qid == "additional_thoughts":
            continue
        transcript_block += f"{qid} ({q_map.get(qid, '')}): {ans}\n\n"

    user_prompt = f"""\
{transcript_block}

Score the four dimensions and return this JSON:
{{
  "purchase_intent": <0 or 1>,
  "primary_objection": <0 or 1>,
  "fit_tier_alignment": <0 or 1>,
  "use_case_specificity": <0 or 1>
}}"""

    return system_prompt, user_prompt
