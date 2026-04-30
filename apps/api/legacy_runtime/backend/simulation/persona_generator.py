"""Lightweight deterministic persona generation for mock simulation realism."""

from __future__ import annotations

from typing import List, Optional

from backend.grounding.prior_sampler import (
    get_last_prior_loading_notes,
    load_grounding_priors,
    sample_grounded_trait_bundles,
)
from backend.schemas import AudienceFilter, GeographyContext, PersonaProfile


DEFAULT_LIFESTYLE_TAGS = ["Family", "Tech-forward", "Budget-conscious", "Wellness", "Sustainability"]
DEFAULT_HOME_TYPES = ["Apartment", "Condo", "Single-family"]
DEFAULT_WORK_MODES = ["remote", "hybrid", "onsite"]


_LAST_PERSONA_PRIOR_NOTES: list[dict] = []


def generate_persona_profiles(
    audience_filter: Optional[AudienceFilter],
    sample_size: int,
    use_grounded_priors: bool = True,
    seed: int | None = None,
    geography_context: GeographyContext | None = None,
    use_geography_filtered_priors: bool = True,
    use_cex_affordability_priors: bool = True,
) -> List[PersonaProfile]:
    """Generate deterministic persona profiles from audience constraints.

    Grounded integration strategy:
    - Prefer prior-based grounded trait bundle seeding when available.
    - Apply existing heuristic enrichment (lifestyle/use-case/barrier/segment) on top.
    - Fall back to legacy rule-based generation if grounded priors are unavailable.
    """
    profiles, _mode = generate_persona_profiles_with_mode(
        audience_filter=audience_filter,
        sample_size=sample_size,
        use_grounded_priors=use_grounded_priors,
        seed=seed,
        geography_context=geography_context,
        use_geography_filtered_priors=use_geography_filtered_priors,
        use_cex_affordability_priors=use_cex_affordability_priors,
    )
    return profiles


def generate_persona_profiles_with_mode(
    audience_filter: Optional[AudienceFilter],
    sample_size: int,
    use_grounded_priors: bool = True,
    seed: int | None = None,
    geography_context: GeographyContext | None = None,
    use_geography_filtered_priors: bool = True,
    use_cex_affordability_priors: bool = True,
) -> tuple[List[PersonaProfile], str]:
    """Generate persona profiles and return generation mode for observability.

    Returns:
        tuple[list[PersonaProfile], str]
        mode is one of:
        - "grounded_priors"
        - "heuristic_fallback"
        - "heuristic_only" (when grounded mode is explicitly disabled)
    """
    profiles: List[PersonaProfile] = []
    global _LAST_PERSONA_PRIOR_NOTES
    _LAST_PERSONA_PRIOR_NOTES = []
    if sample_size <= 0:
        return profiles, "heuristic_fallback"

    if use_grounded_priors:
        try:
            priors = load_grounding_priors(
                geography_context=geography_context,
                use_geography_filtered_priors=use_geography_filtered_priors,
            )
            if not use_cex_affordability_priors:
                priors.pop("cex_affordability", None)
                priors.pop("cex_spending", None)
            bundles = sample_grounded_trait_bundles(
                audience_filter=audience_filter or AudienceFilter(),
                priors=priors,
                n=sample_size,
                seed=seed,
                geography_context=None,
                use_geography_filtered_priors=False,
            )
            _LAST_PERSONA_PRIOR_NOTES = get_last_prior_loading_notes()
            if not use_cex_affordability_priors:
                _LAST_PERSONA_PRIOR_NOTES.append(
                    {
                        "prior_table_name": "cex_affordability",
                        "filter_level_used": "global",
                        "row_count_before": 0,
                        "row_count_after": 0,
                        "narrowed": False,
                        "notes": "CEX affordability priors disabled by mode flag.",
                    }
                )
            profiles = _build_profiles_from_grounded_bundles(
                audience_filter=audience_filter,
                bundles=bundles,
            )
            return profiles, "grounded_priors"
        except Exception:
            # Safe explicit fallback when priors are unavailable/malformed.
            _LAST_PERSONA_PRIOR_NOTES = []
            profiles = _build_heuristic_profiles(audience_filter=audience_filter, sample_size=sample_size)
            return profiles, "heuristic_fallback"

    profiles = _build_heuristic_profiles(audience_filter=audience_filter, sample_size=sample_size)
    return profiles, "heuristic_only"


def get_last_persona_prior_notes() -> list[dict]:
    """Return per-table notes captured from the last persona grounded load pass."""
    return [dict(item) for item in _LAST_PERSONA_PRIOR_NOTES]


def grounded_priors_available() -> bool:
    """Return True when grounding prior tables can be loaded."""
    try:
        load_grounding_priors()
        return True
    except Exception:
        return False


def _build_heuristic_profiles(
    audience_filter: Optional[AudienceFilter],
    sample_size: int,
) -> List[PersonaProfile]:
    """Legacy heuristic-only persona generation path."""
    profiles: List[PersonaProfile] = []

    for index in range(1, sample_size + 1):
        ownership = _pick_ownership(audience_filter, index)
        work_mode = _pick_work_mode(audience_filter, index)
        home_type = _pick_home_type(audience_filter, index)
        age_bucket = _pick_age_bucket(audience_filter, index)
        income_bucket = _pick_income_bucket(audience_filter, index)
        lifestyle_tags = _pick_lifestyle_tags(audience_filter, index)

        likely_use_case = _pick_likely_use_case(work_mode=work_mode, lifestyle_tags=lifestyle_tags, home_type=home_type)
        likely_barrier = _pick_likely_barrier(income_bucket=income_bucket, ownership=ownership, home_type=home_type)
        segment_label = _pick_segment_label(
            work_mode=work_mode,
            lifestyle_tags=lifestyle_tags,
            income_bucket=income_bucket,
            likely_use_case=likely_use_case,
        )
        fit_tier = _pick_fit_tier(
            likely_barrier=likely_barrier,
            income_bucket=income_bucket,
            affordability_pressure=None,
            ownership=ownership,
            index=index,
        )
        awareness_stage = _pick_awareness_stage(lifestyle_tags=lifestyle_tags, index=index)

        profiles.append(
            PersonaProfile(
                persona_id=f"PERS_{index:03d}",
                age_bucket=age_bucket,
                income_bucket=income_bucket,
                household_size_bucket=None,
                ownership=ownership,
                home_type=home_type,
                work_mode=work_mode,
                lifestyle_tags=lifestyle_tags,
                likely_use_case=likely_use_case,
                likely_barrier=likely_barrier,
                segment_label=segment_label,
                affordability_pressure=None,
                housing_burden_proxy=None,
                spend_intensity_bucket=None,
                fit_tier=fit_tier,
                awareness_stage=awareness_stage,
            )
        )

    return profiles


def _build_profiles_from_grounded_bundles(
    audience_filter: Optional[AudienceFilter],
    bundles: list[dict[str, str]],
) -> List[PersonaProfile]:
    """Build persona profiles from grounded trait bundles plus heuristic enrichment."""
    profiles: List[PersonaProfile] = []

    for index, bundle in enumerate(bundles, start=1):
        age_bucket = _normalize_grounded_age_bucket(bundle.get("age_bucket"), audience_filter, index)
        income_bucket = _normalize_grounded_income_bucket(bundle.get("income_bucket"), audience_filter, index)
        ownership = _normalize_grounded_ownership(bundle.get("ownership_group"), audience_filter, index)
        home_type = _normalize_grounded_home_type(bundle.get("home_type_group"), audience_filter, index)
        work_mode = _normalize_grounded_work_mode(bundle.get("work_mode_hint"), audience_filter, index)
        household_size_bucket = _normalize_grounded_household_size_bucket(bundle.get("household_size_bucket"))
        affordability_pressure = _normalize_affordability_pressure(bundle.get("affordability_pressure"))
        housing_burden_proxy = _normalize_housing_burden_proxy(bundle.get("housing_burden_proxy"))
        spend_intensity_bucket = _normalize_spend_intensity_bucket(bundle.get("spend_intensity_bucket"))

        lifestyle_tags = _pick_lifestyle_tags(audience_filter, index)
        likely_use_case = _pick_likely_use_case(work_mode=work_mode, lifestyle_tags=lifestyle_tags, home_type=home_type)
        likely_barrier = _pick_likely_barrier(income_bucket=income_bucket, ownership=ownership, home_type=home_type)
        segment_label = _pick_segment_label(
            work_mode=work_mode,
            lifestyle_tags=lifestyle_tags,
            income_bucket=income_bucket,
            likely_use_case=likely_use_case,
        )
        fit_tier = _pick_fit_tier(
            likely_barrier=likely_barrier,
            income_bucket=income_bucket,
            affordability_pressure=affordability_pressure,
            ownership=ownership,
            index=index,
        )
        awareness_stage = _pick_awareness_stage(lifestyle_tags=lifestyle_tags, index=index)

        profiles.append(
            PersonaProfile(
                persona_id=f"PERS_{index:03d}",
                age_bucket=age_bucket,
                income_bucket=income_bucket,
                household_size_bucket=household_size_bucket,
                ownership=ownership,
                home_type=home_type,
                work_mode=work_mode,
                lifestyle_tags=lifestyle_tags,
                likely_use_case=likely_use_case,
                likely_barrier=likely_barrier,
                segment_label=segment_label,
                affordability_pressure=affordability_pressure,
                housing_burden_proxy=housing_burden_proxy,
                spend_intensity_bucket=spend_intensity_bucket,
                fit_tier=fit_tier,
                awareness_stage=awareness_stage,
            )
        )

    return profiles


def _normalize_grounded_age_bucket(value: Optional[str], audience_filter: Optional[AudienceFilter], index: int) -> str:
    """Convert grounded age bucket labels to existing persona age bucket style."""
    mapping = {
        "18_24": "18-29",
        "25_34": "30-44",
        "35_44": "30-44",
        "45_54": "45-59",
        "55_64": "45-59",
        "65_plus": "60+",
    }
    if value in mapping:
        return mapping[value]
    return _pick_age_bucket(audience_filter, index)


def _normalize_grounded_income_bucket(value: Optional[str], audience_filter: Optional[AudienceFilter], index: int) -> str:
    """Normalize grounded income bucket values to the current persona scheme."""
    if value == "upper_middle":
        return "middle"
    if value in {"low", "middle", "high"}:
        return value
    return _pick_income_bucket(audience_filter, index)


def _normalize_grounded_ownership(value: Optional[str], audience_filter: Optional[AudienceFilter], index: int) -> str:
    """Normalize grounded ownership labels."""
    if value in {"owner", "renter"}:
        return value
    return _pick_ownership(audience_filter, index)


def _normalize_grounded_home_type(value: Optional[str], audience_filter: Optional[AudienceFilter], index: int) -> str:
    """Map grounded home type groups into current persona home_type field."""
    mapping = {
        "single_family_like": "Single-family",
        "multifamily_like": "Apartment",
        "mobile_or_other": "Other",
    }
    if value in mapping:
        return mapping[value]
    return _pick_home_type(audience_filter, index)


def _normalize_grounded_work_mode(value: Optional[str], audience_filter: Optional[AudienceFilter], index: int) -> str:
    """Map grounded work mode hints into current persona work_mode field."""
    mapping = {
        "remote_friendly": "remote",
        "commute_based": "onsite",
        "not_working_or_unknown": "hybrid",
    }
    if value in mapping:
        return mapping[value]
    return _pick_work_mode(audience_filter, index)


def _normalize_grounded_household_size_bucket(value: Optional[str]) -> Optional[str]:
    """Normalize sampled household-size bucket labels for persona display."""
    if value in {"1", "2", "3_4", "5_plus", "unknown"}:
        return value
    return None


def _normalize_affordability_pressure(value: Optional[str]) -> Optional[str]:
    if value in {"low_pressure", "moderate_pressure", "high_pressure", "unknown"}:
        return value
    return None


def _normalize_housing_burden_proxy(value: Optional[str]) -> Optional[str]:
    if value in {"low", "moderate", "high", "unknown"}:
        return value
    return None


def _normalize_spend_intensity_bucket(value: Optional[str]) -> Optional[str]:
    if value in {"conservative", "balanced", "stretched", "unknown"}:
        return value
    return None


def _pick_ownership(audience_filter: Optional[AudienceFilter], index: int) -> str:
    if audience_filter and audience_filter.homeowner_only:
        return "owner"
    if audience_filter and audience_filter.renter_only:
        return "renter"
    return "owner" if index % 3 != 0 else "renter"


def _pick_work_mode(audience_filter: Optional[AudienceFilter], index: int) -> str:
    if audience_filter and audience_filter.work_from_home is True:
        return "remote"
    if audience_filter and audience_filter.work_from_home is False:
        return "onsite"
    return DEFAULT_WORK_MODES[(index - 1) % len(DEFAULT_WORK_MODES)]


def _pick_home_type(audience_filter: Optional[AudienceFilter], index: int) -> str:
    if audience_filter and audience_filter.home_type:
        return audience_filter.home_type
    return DEFAULT_HOME_TYPES[(index - 1) % len(DEFAULT_HOME_TYPES)]


def _pick_age_bucket(audience_filter: Optional[AudienceFilter], index: int) -> str:
    if audience_filter and audience_filter.age_min is not None and audience_filter.age_max is not None:
        midpoint = (audience_filter.age_min + audience_filter.age_max) / 2
        if midpoint < 30:
            return "18-29"
        if midpoint < 45:
            return "30-44"
        if midpoint < 60:
            return "45-59"
        return "60+"
    buckets = ["18-29", "30-44", "45-59", "60+"]
    return buckets[(index - 1) % len(buckets)]


def _pick_income_bucket(audience_filter: Optional[AudienceFilter], index: int) -> str:
    if audience_filter and audience_filter.income_min is not None and audience_filter.income_max is not None:
        midpoint = (audience_filter.income_min + audience_filter.income_max) / 2
        if midpoint < 60000:
            return "low"
        if midpoint < 120000:
            return "middle"
        return "high"

    if audience_filter and audience_filter.income_max is not None and audience_filter.income_max < 80000:
        return "low"
    if audience_filter and audience_filter.income_min is not None and audience_filter.income_min >= 120000:
        return "high"

    buckets = ["low", "middle", "high"]
    return buckets[(index - 1) % len(buckets)]


def _pick_lifestyle_tags(audience_filter: Optional[AudienceFilter], index: int) -> list[str]:
    if audience_filter and audience_filter.lifestyle_tags:
        tags = audience_filter.lifestyle_tags
        first = tags[(index - 1) % len(tags)]
        if len(tags) == 1:
            return [first]
        second = tags[index % len(tags)]
        return [first] if first == second else [first, second]

    first = DEFAULT_LIFESTYLE_TAGS[(index - 1) % len(DEFAULT_LIFESTYLE_TAGS)]
    second = DEFAULT_LIFESTYLE_TAGS[index % len(DEFAULT_LIFESTYLE_TAGS)]
    return [first] if first == second else [first, second]


def _pick_likely_use_case(work_mode: str, lifestyle_tags: list[str], home_type: str) -> str:
    tags_lower = {tag.lower() for tag in lifestyle_tags}
    if work_mode == "remote":
        return "home office"
    if "wellness" in tags_lower:
        return "wellness studio"
    if "family" in tags_lower:
        return "guest room"
    if home_type.lower().startswith("apartment"):
        return "space optimization"
    return "home office"


def _pick_likely_barrier(income_bucket: str, ownership: str, home_type: str) -> str:
    if income_bucket == "low":
        return "cost"
    if ownership == "renter":
        return "landlord restrictions"
    if home_type.lower().startswith("apartment"):
        return "limited space"
    return "unclear ROI"


def _pick_segment_label(work_mode: str, lifestyle_tags: list[str], income_bucket: str, likely_use_case: str) -> str:
    tags_lower = {tag.lower() for tag in lifestyle_tags}
    if work_mode == "remote":
        return "Remote Professionals"
    if "wellness" in tags_lower:
        return "Wellness-Oriented"
    if income_bucket == "low":
        return "Budget-Conscious"
    if likely_use_case == "guest room":
        return "Family Upgraders"
    return "Balanced Mainstream"


def _pick_fit_tier(
    likely_barrier: Optional[str],
    income_bucket: str,
    affordability_pressure: Optional[str],
    ownership: str,
    index: int = 0,
) -> str:
    if ownership == "renter" and likely_barrier == "landlord restrictions":
        return "edge"
    if likely_barrier in (None, "unclear ROI") and affordability_pressure != "high_pressure":
        return "strong"
    if affordability_pressure == "high_pressure":
        return "latent"
    tier = "soft"
    if index % 7 == 0:
        tier = "strong"
    return tier


def _pick_awareness_stage(lifestyle_tags: list[str], index: int) -> str:
    if "tech-forward" in {t.lower() for t in lifestyle_tags}:
        return "aware"
    return ["aware", "unaware", "aware", "unaware", "aware"][(index - 1) % 5]
