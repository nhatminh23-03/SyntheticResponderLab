"""Build system and user prompts for synthetic depth-interview generation.

Converts a PersonaProfile (grounded from ACS/AHS/CEX priors) into a
role-play system prompt, and formats a list of interview questions into
a user prompt that requests structured JSON responses.
"""

from __future__ import annotations

from typing import Any, Optional


# ---------------------------------------------------------------------------
# Default interview questions
# ---------------------------------------------------------------------------

_FIT_TIER_SENTENCES: dict[str, str] = {
    "strong": " You are actively interested in solving this problem and have been researching solutions.",
    "soft":   " You recognize the problem but have real concerns — cost, space, or unclear value — that have kept you from buying.",
    "latent": " You have the underlying need but have never thought of it as something a product could solve.",
    "edge":   " You have an adjacent use case and are curious, but you are not sure this product is really meant for someone like you.",
}

_AWARENESS_SENTENCES: dict[str, str] = {
    "aware":   " You are familiar with products in this category and have formed opinions about what works and what does not.",
    "unaware": " You are not aware that solutions like this exist, though you may have the underlying need.",
}


DEFAULT_QUESTIONS: list[dict[str, str]] = [
    {
        "id": "IQ1",
        "text": "How do you currently use [product_category] or similar solutions? "
                "What's your relationship with them day-to-day?",
    },
    {
        "id": "IQ2",
        "text": "What unmet needs or frustrations do you have that [product_name] could address?",
    },
    {
        "id": "IQ3",
        "text": "Have you considered similar products or solutions before? "
                "What happened — did you buy, and if not, why not?",
    },
    {
        "id": "IQ4",
        "text": "If you could design the ideal version of [product_name] for your situation, "
                "what would it look like and how would you use it?",
    },
    {
        "id": "IQ5",
        "text": "How does [product_name] fit into your work-life balance or daily routine? "
                "What would change if you had it?",
    },
    {
        "id": "IQ6",
        "text": "What's your honest first reaction to [product_name] at [price_range]? "
                "What stands out — positively or negatively?",
    },
    {
        "id": "IQ7",
        "text": "What would be your biggest concerns or deal-breakers? "
                "And what would need to be true for you to actually buy it?",
    },
    {
        "id": "IQ8",
        "text": "How would you discover something like this, and who would you talk to about it?",
    },
]


def resolve_questions(
    questions: list[dict[str, str]] | None,
    bpc: Any | None,
) -> list[dict[str, str]]:
    """Return resolved question list with placeholders filled from product context."""
    base = questions if questions else DEFAULT_QUESTIONS

    product_name = ""
    product_category = ""
    price_range = ""
    if bpc:
        product_name = getattr(bpc, "product_name", "") or ""
        product_category = getattr(bpc, "product_type", "") or getattr(bpc, "industry", "") or ""
        price_range = getattr(bpc, "price_range", "") or ""

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

def build_system_prompt(persona: Any, bpc: Any | None, audience: Any | None) -> str:
    """Build a persona role-play system prompt from a PersonaProfile."""

    # --- Persona traits ---
    age = getattr(persona, "age_bucket", None) or "unknown age"
    income = getattr(persona, "income_bucket", None) or "unknown income"
    ownership = getattr(persona, "ownership", None) or "unknown tenure"
    work_mode = getattr(persona, "work_mode", None) or "unknown work arrangement"
    home_type = getattr(persona, "home_type", None) or "unknown home type"
    segment = getattr(persona, "segment_label", None) or ""
    lifestyle_tags = getattr(persona, "lifestyle_tags", []) or []
    use_case = getattr(persona, "likely_use_case", None) or ""
    barrier = getattr(persona, "likely_barrier", None) or ""
    affordability = getattr(persona, "affordability_pressure", None) or ""
    fit_tier = getattr(persona, "fit_tier", None) or ""
    awareness_stage = getattr(persona, "awareness_stage", None) or ""

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
    if fit_tier in _FIT_TIER_SENTENCES:
        persona_desc += _FIT_TIER_SENTENCES[fit_tier]
    if awareness_stage in _AWARENESS_SENTENCES:
        persona_desc += _AWARENESS_SENTENCES[awareness_stage]

    # --- Product context ---
    product_context = ""
    if bpc:
        product_name = getattr(bpc, "product_name", "") or ""
        description = getattr(bpc, "product_description", "") or ""
        price_range = getattr(bpc, "price_range", "") or ""
        target = getattr(bpc, "target_customer", "") or ""
        features = getattr(bpc, "key_features", []) or []
        visual_labels = getattr(bpc, "product_image_labels", []) or []
        visual_objects = getattr(bpc, "product_image_objects", []) or []
        visual_colors = getattr(bpc, "product_image_colors", []) or []

        if product_name or description or features or visual_labels or visual_objects or visual_colors:
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

    # --- Audience context (geography/lifestyle notes) ---
    audience_context = ""
    if audience:
        notes = getattr(audience, "notes", "") or ""
        state = getattr(audience, "state", "") or ""
        metro = getattr(audience, "metro", "") or ""
        location_parts = [p for p in [metro, state] if p]
        if location_parts:
            audience_context = f"\n\nYou are based in {', '.join(location_parts)}."
        if notes:
            audience_context += f" Additional context: {notes}"

    system_prompt = f"""\
You are role-playing as a real person participating in a qualitative depth interview.

YOUR PERSONA:
{persona_desc}{audience_context}{product_context}

INSTRUCTIONS:
- Stay fully in character throughout the interview. Answer authentically based on your persona.
- Be specific and personal — use first-person language, share genuine opinions, hesitations, and enthusiasm where appropriate.
- Do NOT give generic marketing-speak answers. Reflect the real tensions, trade-offs, and priorities your persona would have.
- Keep each answer substantive: 3–6 sentences minimum, conversational in tone.
- When asked about the product, engage with it honestly — you may be skeptical, curious, excited, or uncertain depending on your situation.
- You will be given a JSON schema to follow. Return ONLY valid JSON — no preamble, no markdown fences."""

    return system_prompt


def build_user_prompt(questions: list[dict[str, str]]) -> str:
    """Build the user prompt listing interview questions and requesting JSON output."""

    question_lines = "\n".join(
        f'{q["id"]}: {q["text"]}' for q in questions
    )

    answer_keys = ", ".join(f'"{q["id"]}": "<your answer>"' for q in questions)

    user_prompt = f"""\
Please answer each of the following interview questions as your persona.

INTERVIEW QUESTIONS:
{question_lines}

Return your answers as a single JSON object with exactly these keys:
{{
  {answer_keys},
  "additional_thoughts": "<anything else you want to add — optional, can be empty string>"
}}

IMPORTANT: Return ONLY the JSON object. No markdown, no commentary outside the JSON."""

    return user_prompt
