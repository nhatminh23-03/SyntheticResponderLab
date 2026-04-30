"""Study-mode presets for Neo Smart Living demo flows.

This module defines defaults used to prefill UI forms when the user selects
Neo Smart Living demo mode. These presets are UI convenience only.
"""

from __future__ import annotations

from pathlib import Path

from backend.schemas import AudienceFilter, BusinessProductContext, MarketContext, ResearchBrief, SurveySchema
from backend.survey.parser import parse_uploaded_survey
from backend.survey.schema_normalizer import normalize_survey_payload
from backend.survey.validator import validate_survey_schema


def get_neo_audience_defaults() -> AudienceFilter:
    """Return Neo Smart Living default audience constraints."""
    return AudienceFilter(
        state=None,
        metro=None,
        zip_code=None,
        age_min=25,
        age_max=64,
        income_min=50000,
        income_max=199999,
        homeowner_only=True,
        renter_only=False,
        work_from_home=None,
        lifestyle_tags=[
            "remote work",
            "home improvement",
            "wellness",
            "hosting guests",
            "storage",
            "outdoor lifestyle",
        ],
        home_type="Single-family",
        notes=(
            "Neo benchmark default: backyard-space-compatible homeowners, broad geography "
            "(not locked to a specific state or metro)."
        ),
    )


def get_neo_business_product_defaults() -> BusinessProductContext:
    """Return Neo Smart Living default business/product context."""
    return BusinessProductContext(
        business_name="Neo Smart Living",
        industry="Factory-built modular backyard structures",
        product_name="Tahoe Mini",
        product_type="Permit-light modular backyard studio",
        product_description=(
            "Tahoe Mini is a compact ~117 sq ft factory-built backyard unit delivered as "
            "flat-pack panels and typically installed in about one day. It is positioned as "
            "a non-habitable accessory structure (not an ADU), with no plumbing and no kitchen."
        ),
        target_customer="Homeowners with usable backyard/property space",
        price_range="$23,000 delivered and installed",
        primary_goal="Validate demand, barriers, and strongest positioning for Tahoe Mini.",
        key_features=[
            "~117 sq ft compact footprint",
            "Flat-pack delivery and fast install",
            "Modular interchangeable wall system",
            "Pre-wired electrical",
            "Smart entry lock",
            "Dual-pane floor-to-ceiling glass",
            "Pitched roof with drainage",
            "Optional sound insulation and HVAC",
        ],
        main_use_cases=[
            "Home office",
            "Guest suite / short-term stay",
            "Wellness studio",
            "Adventure gear basecamp",
            "General storage / premium speed shed",
            "Creative studio",
        ],
        main_pain_points_solved=[
            "Need extra functional space without full remodel",
            "Desire simpler/faster path versus traditional construction",
            "Need flexible backyard use cases",
        ],
        main_barriers_or_concerns=[
            "Upfront cost",
            "HOA restrictions",
            "Permit uncertainty",
            "Space/access constraints",
            "Financing options",
            "Quality and durability concerns",
            "Resale uncertainty",
        ],
        product_image_labels=[
            "Prefabricated building",
            "Modular structure",
            "Wood panel",
            "Glass door",
            "Backyard",
            "Outdoor structure",
            "Shed",
            "Architecture",
            "Property",
            "Garden",
        ],
        notes="Preset from Neo Smart Living challenge docs for demo mode.",
    )


def get_neo_market_defaults() -> MarketContext:
    """Return Neo Smart Living default competitor/market context."""
    return MarketContext(
        category="Backyard prefab studio / permit-light accessory structure",
        typical_price_band="$20,000-$35,000 (varies by install scope and options)",
        substitutes=[
            "Traditional shed",
            "Shed conversion",
            "Garage conversion",
            "Room reallocation / remodel",
            "Home renovation/addition",
            "Full ADU build",
            "Off-site coworking or rented studio",
            "Off-site wellness/gym/studio alternatives",
        ],
        common_expected_features=[
            "Natural light and usable interior layout",
            "Durability and weather resistance",
            "Electrical readiness",
            "Fast installation",
            "Clear permitting guidance",
            "Simple setup",
            "Financing options",
            "Customization options",
        ],
        common_objections=[
            "Price sensitivity",
            "Permit/HOA uncertainty",
            "HOA restrictions",
            "Backyard access limitations",
            "Financing availability",
            "Durability concerns",
            "Unclear resale value",
            "Quality trust concerns",
        ],
        notes="Preset market frame for Neo Smart Living demo runs.",
    )


def get_neo_research_brief_defaults() -> ResearchBrief:
    """Return Neo Smart Living default research brief for Tahoe Mini interviews."""
    return ResearchBrief(
        primary_question=(
            "Who is most likely to buy the Tahoe Mini, and what would make them pull the trigger?"
        ),
        hypotheses=[
            "Remote and hybrid workers are the strongest fit — they need dedicated workspace separation.",
            "Upfront price ($23K) is the single biggest barrier across all segments.",
            "Strong-fit buyers already have a specific use case in mind before discovering the product.",
            "HOA uncertainty and permit complexity create hesitation even among interested buyers.",
            "Financing availability would meaningfully expand the addressable market.",
        ],
        decisions_to_inform=[
            "Which use case to lead with in marketing (home office vs. guest suite vs. wellness).",
            "How to frame pricing and financing in the first touchpoint.",
            "Which objections to address first in sales conversations.",
            "Whether to prioritize strong-fit or soft-fit segments in initial campaigns.",
        ],
        focus_fit_tiers=["strong", "soft"],
        focus_segments=[],
        known_context=(
            "Tahoe Mini is a ~117 sq ft factory-built backyard studio at $23K delivered and installed. "
            "It is permit-light, non-habitable (no plumbing/kitchen), and positions against full ADUs "
            "and traditional sheds. All 30 interviewees are SoCal homeowners aged 25–64."
        ),
        notes="Neo Smart Living demo preset. Covers Tahoe Mini demand validation study.",
    )


def get_neo_survey_markdown_path() -> Path:
    """Return the default Neo survey markdown path used for preset loading."""
    project_root = Path(__file__).resolve().parents[1]
    return project_root / "Provided Info" / "Neo Smart Living — Survey_HighPriority.md"


def get_neo_survey_schema_default() -> SurveySchema:
    """Parse and return the default Neo survey schema from bundled markdown."""
    survey_path = get_neo_survey_markdown_path()
    raw_payload = parse_uploaded_survey(
        file_name=survey_path.name,
        file_bytes=survey_path.read_bytes(),
    )
    normalized_schema = normalize_survey_payload(raw_payload)
    return validate_survey_schema(normalized_schema)
