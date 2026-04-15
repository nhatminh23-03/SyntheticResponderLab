from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.persistence.models import Job, PersonaPreviewRun, Study, StudySectionState
from src.services.ids import make_public_id
from src.simulation.interview_prompt_builder import DEFAULT_QUESTIONS, resolve_questions

DEMO_MODEL_A = "openai/gpt-4.1-mini"
DEMO_MODEL_B = "google/gemini-2.5-flash"
DEMO_JUDGE_MODEL = "demo/stamp-fixture"
GROUNDING_THRESHOLD = 0.67
PROTOTYPE_TRANSCRIPTS_PATH = Path("apps/api/demo_data/prototype/interview_transcripts.csv")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_demo_interview_run(
    session: Session,
    study: Study,
    *,
    latest_preview: PersonaPreviewRun,
    product: dict | None,
    questions: list[dict[str, str]] | None = None,
) -> Job:
    existing = session.scalar(
        select(Job)
        .where(Job.study_id == study.id, Job.job_type == "interview_run")
        .order_by(Job.queued_at.desc())
    )
    if existing and existing.status == "completed" and (existing.payload_json or {}).get("demo_fixture"):
        _seed_demo_interview_insights(
            session,
            study,
            job_public_id=existing.public_id,
            result=existing.result_json or {},
        )
        return existing

    result = _build_demo_interview_result(
        latest_preview=latest_preview,
        product=product,
        questions=questions,
    )
    job = Job(
        public_id=make_public_id("job"),
        study_id=study.id,
        job_type="interview_run",
        status="completed",
        payload_json={
            "persona_count": result["persona_count"],
            "model_a": result["model_a"],
            "model_b": result["model_b"],
            "judge_model": result["judge_model"],
            "custom_questions": bool(questions),
            "demo_fixture": True,
        },
        result_json=result,
        error_json=None,
        queued_at=utcnow(),
        started_at=utcnow(),
        completed_at=utcnow(),
    )
    session.add(job)
    session.flush()
    _seed_demo_interview_insights(
        session,
        study,
        job_public_id=job.public_id,
        result=result,
    )
    study.updated_at = utcnow()
    session.add(study)
    return job


def _build_demo_interview_result(
    *,
    latest_preview: PersonaPreviewRun,
    product: dict | None,
    questions: list[dict[str, str]] | None,
) -> Dict[str, Any]:
    resolved_questions = resolve_questions(questions or DEFAULT_QUESTIONS, product)
    prototype_rows = _load_prototype_transcript_rows()

    if prototype_rows:
        pairs = _build_pairs_from_prototype(
            prototype_rows=prototype_rows,
            preview_personas=sorted(latest_preview.personas, key=lambda item: item.row_index),
            resolved_questions=resolved_questions,
        )
    else:
        pairs = _build_pairs_from_generated_fixture(
            preview_personas=sorted(latest_preview.personas, key=lambda item: item.row_index),
            resolved_questions=resolved_questions,
        )

    return {
        "pairs": pairs,
        "grounding_report": _build_grounding_report(pairs),
        "persona_count": len(pairs),
        "model_a": DEMO_MODEL_A,
        "model_b": DEMO_MODEL_B,
        "judge_model": DEMO_JUDGE_MODEL,
        "demo_fixture": True,
        "fixture_source": "prototype_zip" if prototype_rows else "generated_fallback",
    }


def _build_pairs_from_generated_fixture(
    *,
    preview_personas: list[Any],
    resolved_questions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []

    for index, preview_persona in enumerate(preview_personas):
        persona = preview_persona.persona_json
        profile = _derive_persona_profile(persona)
        pairs.append(
            {
                "persona_id": preview_persona.persona_id,
                "persona_index": index,
                "persona": persona,
                "model_a": {
                    "model": DEMO_MODEL_A,
                    "answers": _build_answers(
                        persona=persona,
                        profile=profile,
                        questions=resolved_questions,
                        variant="a",
                    ),
                    "error": None,
                },
                "model_b": {
                    "model": DEMO_MODEL_B,
                    "answers": _build_answers(
                        persona=persona,
                        profile=profile,
                        questions=resolved_questions,
                        variant="b",
                    ),
                    "error": None,
                },
                "generation_timestamp": utcnow().isoformat(),
            }
        )

    return pairs


def _build_pairs_from_prototype(
    *,
    prototype_rows: list[dict[str, str]],
    preview_personas: list[Any],
    resolved_questions: list[dict[str, str]],
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    selected_rows = prototype_rows[: len(preview_personas)]

    for index, (preview_persona, row) in enumerate(zip(preview_personas, selected_rows)):
        persona = preview_persona.persona_json
        profile = _derive_persona_profile(persona)
        source_answers = _extract_answers_from_row(row)
        source_model = _normalize_model_name(row.get("model"))
        companion_model = DEMO_MODEL_B if source_model == DEMO_MODEL_A else DEMO_MODEL_A

        pairs.append(
            {
                "persona_id": preview_persona.persona_id,
                "persona_index": index,
                "persona": persona,
                "model_a": {
                    "model": source_model,
                    "answers": source_answers,
                    "error": None,
                },
                "model_b": {
                    "model": companion_model,
                    "answers": _build_companion_answers_from_source(
                        answers=source_answers,
                        profile=profile,
                    ),
                    "error": None,
                },
                "generation_timestamp": row.get("generation_timestamp") or utcnow().isoformat(),
                "source_fixture_persona_id": row.get("persona_id"),
                "source_fixture_model": row.get("model"),
            }
        )

    return pairs


def _load_prototype_transcript_rows() -> list[dict[str, str]]:
    transcripts_path = _prototype_transcripts_path()
    if transcripts_path is None:
        return []
    raw = transcripts_path.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))


def _prototype_transcripts_path() -> Optional[Path]:
    root = Path(__file__).resolve().parents[4]
    candidate = root / PROTOTYPE_TRANSCRIPTS_PATH
    return candidate if candidate.exists() else None


def _extract_answers_from_row(row: dict[str, str]) -> Dict[str, str]:
    answers: Dict[str, str] = {}
    for q in DEFAULT_QUESTIONS:
        qid = q["id"]
        value = (row.get(qid) or "").strip()
        answers[qid] = value or f"[No response provided for {qid}]"

    additional = (row.get("additional_thoughts") or "").strip()
    if additional:
        answers["additional_thoughts"] = additional
    return answers


def _normalize_model_name(model_name: Optional[str]) -> str:
    value = (model_name or "").strip().lower()
    if "gemini" in value:
        return DEMO_MODEL_B
    return DEMO_MODEL_A


def _build_companion_answers_from_source(
    *,
    answers: Dict[str, str],
    profile: Dict[str, str],
) -> Dict[str, str]:
    companion: Dict[str, str] = {}
    for qid, answer in answers.items():
        if qid == "additional_thoughts":
            companion[qid] = (
                f"{answer.rstrip()} The remaining question for me is still {profile['barrier']}."
            )
            continue
        companion[qid] = _lightly_rephrase_answer(answer=answer, qid=qid, profile=profile)
    return companion


def _lightly_rephrase_answer(
    *,
    answer: str,
    qid: str,
    profile: Dict[str, str],
) -> str:
    text = re.sub(r"\s+", " ", answer.strip())
    if not text:
        return f"I still come back to {profile['use_case']} and {profile['barrier']}."

    suffix_by_qid = {
        "IQ1": "The separation from the main house is what keeps pulling me back.",
        "IQ2": "That is the unmet need I would pay to solve.",
        "IQ3": "The comparison always comes back to cost and uncertainty.",
        "IQ4": "Flexibility over time matters almost as much as the first use case.",
        "IQ5": "The routine benefit feels as important as the physical structure itself.",
        "IQ6": "That is why I keep weighing value against confidence.",
        "IQ7": f"My main watchout is still {profile['barrier']}.",
        "IQ8": "I would trust proof from real owners more than polished marketing.",
    }
    suffix = suffix_by_qid.get(qid, f"The open issue for me is still {profile['barrier']}.")
    if text.endswith((".", "!", "?")):
        return f"{text} {suffix}"
    return f"{text}. {suffix}"


def _derive_persona_profile(persona: dict[str, Any]) -> Dict[str, str]:
    lifestyle_tags = [str(tag).lower() for tag in (persona.get("lifestyle_tags") or [])]
    work_mode = str(persona.get("work_mode") or "").lower()
    fit_tier = str(persona.get("fit_tier") or "soft").lower()
    likely_use_case = str(persona.get("likely_use_case") or "").strip()
    likely_barrier = str(persona.get("likely_barrier") or "").strip()
    segment_label = str(persona.get("segment_label") or "homeowners").strip()

    if likely_use_case:
        use_case = likely_use_case
    elif work_mode in {"remote", "hybrid"}:
        use_case = "a dedicated backyard office that separates work from home life"
    elif any("wellness" in tag or "fitness" in tag or "yoga" in tag for tag in lifestyle_tags):
        use_case = "a private wellness and workout studio"
    elif any("guest" in tag or "hosting" in tag for tag in lifestyle_tags):
        use_case = "a guest-ready flex space for visiting friends and family"
    elif any("outdoor" in tag or "adventure" in tag or "gear" in tag for tag in lifestyle_tags):
        use_case = "a secure gear room and weekend basecamp"
    else:
        use_case = "a flexible extra room that can shift between office, studio, and storage"

    if likely_barrier:
        barrier = likely_barrier
    elif fit_tier == "strong":
        barrier = "getting confident about permit and HOA details before moving ahead"
    elif fit_tier == "soft":
        barrier = "the upfront price and whether financing makes the math comfortable"
    elif fit_tier == "latent":
        barrier = "proving I would use it enough to justify the spend"
    else:
        barrier = "whether the footprint really fits my property and priorities"

    if fit_tier == "strong":
        intent = "I can picture buying something like this if the site fit checks out."
    elif fit_tier == "soft":
        intent = "I like the idea, but I still need the value equation to feel airtight."
    elif fit_tier == "latent":
        intent = "I am curious, though I am not naturally in market without a sharper trigger."
    else:
        intent = "It is interesting, but I would need a stronger reason to make room for it."

    return {
        "fit_tier": fit_tier,
        "segment_label": segment_label,
        "use_case": use_case,
        "barrier": barrier,
        "intent": intent,
    }


def _build_answers(
    *,
    persona: dict[str, Any],
    profile: Dict[str, str],
    questions: list[dict[str, str]],
    variant: str,
) -> Dict[str, str]:
    answers: Dict[str, str] = {}
    for question in questions:
        qid = question["id"]
        qtext = question["text"].lower()
        answers[qid] = _build_answer_text(
            persona=persona,
            profile=profile,
            qid=qid,
            qtext=qtext,
            variant=variant,
        )

    if variant == "a":
        answers["additional_thoughts"] = (
            f"My overall reaction is that this feels most compelling for {profile['use_case']}, "
            f"but I would still need clarity on {profile['barrier']}."
        )
    else:
        answers["additional_thoughts"] = (
            f"I keep coming back to the flexibility of the space. The open question for me is {profile['barrier']}."
        )
    return answers


def _build_answer_text(
    *,
    persona: dict[str, Any],
    profile: Dict[str, str],
    qid: str,
    qtext: str,
    variant: str,
) -> str:
    persona_id = str(persona.get("persona_id") or "this persona")
    work_mode = str(persona.get("work_mode") or "mixed").replace("-", " ")
    segment = profile["segment_label"]
    use_case = profile["use_case"]
    barrier = profile["barrier"]
    intent = profile["intent"]

    if qid == "IQ1" or "currently use" in qtext or "relationship" in qtext:
        if variant == "a":
            return (
                f"As {segment.lower()}, I currently patch together space inside the house for {use_case}. "
                f"That works, but it means noise, interruptions, and no real separation from daily life."
            )
        return (
            f"Right now I am improvising. I use whatever room is available for {use_case}, "
            f"and that starts to feel cramped or distracting after a full day."
        )

    if qid == "IQ2" or "frustrations" in qtext or "unmet needs" in qtext:
        if variant == "a":
            return (
                f"The unmet need is a space that feels purpose-built instead of temporary. "
                f"I want privacy, a cleaner routine, and something that does not take over the main house."
            )
        return (
            f"What stands out is the chance to create dedicated space without a full remodel. "
            f"The friction today is juggling storage, focus, and daily household overlap."
        )

    if qid == "IQ3" or "considered similar" in qtext or "did you buy" in qtext:
        if variant == "a":
            return (
                f"I have looked at sheds, garage conversions, and a few prefab studios. "
                f"I usually stop once the project starts to feel expensive or uncertain around {barrier}."
            )
        return (
            f"I have definitely looked at alternatives. The usual pattern is that cheaper options look rough, "
            f"and premium options look good but push me back into concerns about {barrier}."
        )

    if qid == "IQ4" or "ideal version" in qtext or "what would it look like" in qtext:
        if variant == "a":
            return (
                f"My ideal version would support {use_case}, have strong natural light, and still leave enough wall space "
                f"for practical storage. I would want it to feel calm and finished rather than temporary."
            )
        return (
            f"I would design it around {use_case}: good daylight, strong insulation, simple power setup, "
            f"and enough flexibility that it could change roles later."
        )

    if qid == "IQ5" or "daily routine" in qtext or "what would change" in qtext:
        if variant == "a":
            return (
                f"It would create real separation in my routine. For someone working {work_mode}, "
                f"having that extra zone would make the house feel less crowded and more intentional."
            )
        return (
            f"The biggest change would be reclaiming the main house. I could keep {use_case} outside the core living area "
            f"and make day-to-day life feel more organized."
        )

    if qid == "IQ6" or "first reaction" in qtext or "price" in qtext:
        if variant == "a":
            return (
                f"My honest first reaction is that the concept is strong, but the price means I need confidence in durability, "
                f"speed of install, and long-term use. {intent}"
            )
        return (
            f"At this price I am not treating it like an impulse decision. I would compare it against remodel headaches "
            f"and how often I would actually use the space. {intent}"
        )

    if qid == "IQ7" or "deal-breakers" in qtext or "what would need to be true" in qtext:
        if variant == "a":
            return (
                f"My biggest concern is {barrier}. To buy, I would need proof that installation is predictable, "
                f"the structure lasts, and the setup works on my actual property."
            )
        return (
            f"The deal-breakers are mostly around {barrier}. I would move forward faster if Neo showed clear case studies, "
            f"transparent install steps, and realistic examples for homeowners like {persona_id}."
        )

    if qid == "IQ8" or "discover" in qtext or "who would you talk to" in qtext:
        if variant == "a":
            return (
                "I would probably discover it through backyard office or prefab research, then validate it with my partner, "
                "a few homeowner friends, and whatever permit or HOA guidance applies locally."
            )
        return (
            "I would hear about it through search, social proof, or targeted ads around backyard upgrades. "
            "Before buying, I would compare reviews and talk it through with household decision-makers."
        )

    if variant == "a":
        return (
            f"This feels relevant for {use_case}. My main hesitation is {barrier}, but the concept is directionally compelling."
        )
    return (
        f"I see the appeal, especially for {use_case}. The open issue for me is still {barrier}."
    )


def _build_grounding_report(pairs: list[dict[str, Any]]) -> Dict[str, Any]:
    persona_scores = []
    for pair in pairs:
        fit_tier = str(pair.get("persona", {}).get("fit_tier") or "soft").lower()
        if fit_tier == "strong":
            dimensions = {
                "purchase_intent": 1,
                "primary_objection": 1,
                "fit_tier_alignment": 1,
                "use_case_specificity": 1,
            }
        elif fit_tier == "soft":
            dimensions = {
                "purchase_intent": 1,
                "primary_objection": 1,
                "fit_tier_alignment": 1,
                "use_case_specificity": 0,
            }
        elif fit_tier == "latent":
            dimensions = {
                "purchase_intent": 0,
                "primary_objection": 1,
                "fit_tier_alignment": 1,
                "use_case_specificity": 0,
            }
        else:
            dimensions = {
                "purchase_intent": 0,
                "primary_objection": 1,
                "fit_tier_alignment": 0,
                "use_case_specificity": 0,
            }

        score = sum(dimensions.values()) / 4
        persona_scores.append(
            {
                "persona_id": pair["persona_id"],
                "score": round(score, 4),
                "dimension_scores": dimensions,
                "has_error": False,
            }
        )

    if not persona_scores:
        return {
            "corpus_average": 0.0,
            "passes_threshold": False,
            "threshold": GROUNDING_THRESHOLD,
            "per_dimension_avg": {
                "purchase_intent": 0.0,
                "primary_objection": 0.0,
                "fit_tier_alignment": 0.0,
                "use_case_specificity": 0.0,
            },
            "flagged_persona_ids": [],
            "persona_scores": [],
        }

    per_dimension_avg = {
        dimension: round(
            sum(score["dimension_scores"][dimension] for score in persona_scores)
            / len(persona_scores),
            4,
        )
        for dimension in [
            "purchase_intent",
            "primary_objection",
            "fit_tier_alignment",
            "use_case_specificity",
        ]
    }
    corpus_average = round(
        sum(score["score"] for score in persona_scores) / len(persona_scores), 4
    )
    flagged = [
        score["persona_id"]
        for score in persona_scores
        if score["score"] < GROUNDING_THRESHOLD
    ]
    return {
        "corpus_average": corpus_average,
        "passes_threshold": corpus_average >= GROUNDING_THRESHOLD,
        "threshold": GROUNDING_THRESHOLD,
        "per_dimension_avg": per_dimension_avg,
        "flagged_persona_ids": flagged,
        "persona_scores": persona_scores,
    }


def _seed_demo_interview_insights(
    session: Session,
    study: Study,
    *,
    job_public_id: str,
    result: Dict[str, Any],
) -> None:
    insights = build_demo_interview_insights(job_public_id=job_public_id, result=result)
    key = f"interview_insights_{job_public_id}"
    section = session.scalar(
        select(StudySectionState).where(
            StudySectionState.study_id == study.id,
            StudySectionState.section_key == key,
        )
    )
    if section is None:
        section = StudySectionState(
            study_id=study.id,
            section_key=key,
            status="saved",
            value_json=insights,
            saved_at=utcnow(),
            updated_at=utcnow(),
        )
    else:
        section.status = "saved"
        section.value_json = insights
        section.saved_at = section.saved_at or utcnow()
        section.updated_at = utcnow()
    session.add(section)


def build_demo_interview_insights(
    *,
    job_public_id: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    pairs = list(result.get("pairs") or [])
    grounding = result.get("grounding_report") or {}
    themes = [
        _build_theme(
            label="Dedicated Space Relieves Daily Friction",
            sentiment="positive",
            synthesis=(
                "Respondents consistently value Tahoe Mini as a way to create separation from the main house, "
                "especially for focused work, wellness routines, or multipurpose overflow space."
            ),
            pairs=pairs,
            keyword="separation",
            fallback_qid="IQ5",
        ),
        _build_theme(
            label="Price Needs Strong Value Proof",
            sentiment="negative",
            synthesis=(
                "The $23,000 price point is viable for interested homeowners only when installation simplicity, "
                "durability, and long-term utility feel clearly superior to cheaper alternatives."
            ),
            pairs=pairs,
            keyword="price",
            fallback_qid="IQ6",
        ),
        _build_theme(
            label="Permit And Site Confidence Matter",
            sentiment="negative",
            synthesis=(
                "Even favorable respondents want concrete reassurance around HOA rules, permit-light claims, "
                "and whether the unit will work cleanly on their specific property."
            ),
            pairs=pairs,
            keyword="permit",
            fallback_qid="IQ7",
        ),
        _build_theme(
            label="Flexible Use Cases Expand Appeal",
            sentiment="positive",
            synthesis=(
                "The strongest storyline is flexibility: respondents see Tahoe Mini as a space that can move between "
                "office, guest, wellness, creative, and storage roles over time."
            ),
            pairs=pairs,
            keyword="flex",
            fallback_qid="IQ4",
        ),
    ]

    return {
        "themes": themes,
        "persona_count": len(pairs),
        "grounding_corpus_average": grounding.get("corpus_average"),
        "grounding_passes_threshold": grounding.get("passes_threshold"),
        "generated_from_demo_fixture": True,
        "from_run_id": job_public_id,
    }


def _build_theme(
    *,
    label: str,
    sentiment: str,
    synthesis: str,
    pairs: list[dict[str, Any]],
    keyword: str,
    fallback_qid: str,
) -> Dict[str, Any]:
    quote = ""
    quote_persona_id = ""
    count = 0

    for pair in pairs:
        answers = pair.get("model_a", {}).get("answers") or {}
        matched = False
        for value in answers.values():
            text = str(value or "")
            if keyword.lower() in text.lower():
                matched = True
                if not quote:
                    quote = text
                    quote_persona_id = pair.get("persona_id", "")
                break
        if matched:
            count += 1

    if not quote and pairs:
        fallback_answers = pairs[0].get("model_a", {}).get("answers") or {}
        quote = str(
            fallback_answers.get(fallback_qid)
            or next(iter(fallback_answers.values()), "")
        )
        quote_persona_id = pairs[0].get("persona_id", "")

    if count == 0:
        count = max(1, len(pairs) // 2)

    return {
        "label": label,
        "count": count,
        "synthesis": synthesis,
        "representative_quote": quote,
        "quote_persona_id": quote_persona_id,
        "sentiment": sentiment,
    }
