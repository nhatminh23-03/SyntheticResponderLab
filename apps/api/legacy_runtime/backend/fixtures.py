"""Load pre-generated prototype data into app-yaza schemas.

Reads interview_transcripts.csv from the sibling prototype/ folder and maps
rows to InterviewTranscript and PersonaProfile objects for demo/testing use.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

from backend.schemas import InterviewTranscript, PersonaProfile

# Path: app-yaza/backend/fixtures.py → parents[2] = AI Hackathon 2026/
_PROTOTYPE_CSV = (
    Path(__file__).resolve().parents[2]
    / "prototype"
    / "output"
    / "interview_transcripts.csv"
)

_INTERVIEW_QUESTION_IDS = ["IQ1", "IQ2", "IQ3", "IQ4", "IQ5", "IQ6", "IQ7", "IQ8"]


# ---------------------------------------------------------------------------
# Field mapping helpers
# ---------------------------------------------------------------------------

def _map_work_mode(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower()
    if "remote" in v:
        return "remote"
    if "hybrid" in v:
        return "hybrid"
    if "on-site" in v or "onsite" in v:
        return "on-site"
    if "self-employed" in v or "self employed" in v:
        return "self-employed"
    if "retired" in v:
        return "retired"
    return None


def _extract_home_type(home_situation: Optional[str]) -> Optional[str]:
    if not home_situation:
        return None
    s = home_situation.lower()
    if "condo" in s:
        return "condo"
    if "house" in s:
        return "house"
    return None


def _derive_fit_tier(income_bucket: Optional[str], work_mode: Optional[str]) -> Optional[str]:
    """Derive fit tier from income and work mode.

    strong  — high income + flexible work
    soft    — mid income or flexible work
    latent  — lower income or on-site
    edge    — fallback
    """
    income = income_bucket or ""
    wm = work_mode or ""

    high_income = any(x in income for x in ["$150,000", "$200,000", "$150K", "$200K"])
    mid_income = any(x in income for x in ["$75,000", "$100,000", "$75K", "$100K"])
    low_income = any(x in income for x in ["$50,000", "$50K"])
    flexible = wm in {"remote", "hybrid", "self-employed"}

    if high_income and flexible:
        return "strong"
    if mid_income or flexible:
        return "soft"
    if low_income or wm == "on-site":
        return "latent"
    return "edge"


def _parse_lifestyle_tags(lifestyle_note: Optional[str]) -> list[str]:
    """Split lifestyle note into individual tags."""
    if not lifestyle_note:
        return []
    # Split on commas, slashes, and semicolons
    parts = re.split(r"[,/;]", lifestyle_note)
    return [p.strip() for p in parts if p.strip()]


def _safe_str(value: object) -> Optional[str]:
    s = str(value).strip() if value is not None else ""
    return s or None


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------

def load_prototype_transcripts() -> list[InterviewTranscript]:
    """Load 30 pre-generated interview transcripts from the prototype CSV.

    Returns:
        List of InterviewTranscript objects ready for save_interview_transcripts().

    Raises:
        FileNotFoundError: If the prototype CSV is not found at the expected path.
    """
    if not _PROTOTYPE_CSV.exists():
        raise FileNotFoundError(
            f"Prototype interview CSV not found at:\n{_PROTOTYPE_CSV}\n"
            "Ensure the prototype/ folder is present alongside app-yaza/."
        )

    transcripts: list[InterviewTranscript] = []

    with open(_PROTOTYPE_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            work_mode = _map_work_mode(row.get("work_arrangement"))
            income_bucket = _safe_str(row.get("income"))

            answers: dict[str, str] = {}
            for qid in _INTERVIEW_QUESTION_IDS:
                answers[qid] = _safe_str(row.get(qid)) or "[No response provided]"
            extra = _safe_str(row.get("additional_thoughts"))
            if extra:
                answers["additional_thoughts"] = extra

            transcript = InterviewTranscript(
                interview_id=_safe_str(row.get("interview_id")) or row["persona_id"],
                persona_id=_safe_str(row.get("persona_id")) or "",
                model=_safe_str(row.get("model")) or "unknown",
                age_bucket=_safe_str(row.get("age")),
                income_bucket=income_bucket,
                ownership="own",
                work_mode=work_mode,
                home_type=_extract_home_type(row.get("home_situation")),
                segment_label=None,
                lifestyle_tags=_parse_lifestyle_tags(row.get("lifestyle_note")),
                affordability_pressure=None,
                fit_tier=_derive_fit_tier(income_bucket, work_mode),
                awareness_stage="aware",
                answers=answers,
                generation_timestamp=_safe_str(row.get("generation_timestamp")),
            )
            transcripts.append(transcript)

    return transcripts


def load_prototype_personas() -> list[PersonaProfile]:
    """Load persona profiles derived from the prototype CSV.

    Returns:
        List of PersonaProfile objects ready for save_persona_profiles().

    Raises:
        FileNotFoundError: If the prototype CSV is not found at the expected path.
    """
    if not _PROTOTYPE_CSV.exists():
        raise FileNotFoundError(
            f"Prototype interview CSV not found at:\n{_PROTOTYPE_CSV}\n"
            "Ensure the prototype/ folder is present alongside app-yaza/."
        )

    personas: list[PersonaProfile] = []
    seen: set[str] = set()

    with open(_PROTOTYPE_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            persona_id = _safe_str(row.get("persona_id")) or ""
            if persona_id in seen:
                continue
            seen.add(persona_id)

            work_mode = _map_work_mode(row.get("work_arrangement"))
            income_bucket = _safe_str(row.get("income"))

            persona = PersonaProfile(
                persona_id=persona_id,
                age_bucket=_safe_str(row.get("age")),
                income_bucket=income_bucket,
                household_size_bucket=None,
                ownership="own",
                home_type=_extract_home_type(row.get("home_situation")),
                work_mode=work_mode,
                lifestyle_tags=_parse_lifestyle_tags(row.get("lifestyle_note")),
                likely_use_case=None,
                likely_barrier=None,
                segment_label=None,
                affordability_pressure=None,
                housing_burden_proxy=None,
                spend_intensity_bucket=None,
                fit_tier=_derive_fit_tier(income_bucket, work_mode),
                awareness_stage="aware",
            )
            personas.append(persona)

    return personas
