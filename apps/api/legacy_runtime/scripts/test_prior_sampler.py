"""Utility script to test prior-based grounding trait bundle sampling."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure imports work when script is run from project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.grounding.prior_sampler import (
    load_grounding_priors,
    sample_grounded_trait_bundles,
)
from backend.schemas import AudienceFilter


def main() -> None:
    """Run a few sample cases and print sampled grounded trait bundles."""
    priors = load_grounding_priors()

    cases = [
        (
            "Case A: homeowner + mid-age",
            AudienceFilter(homeowner_only=True, age_min=30, age_max=55),
        ),
        (
            "Case B: renter + work from home",
            AudienceFilter(renter_only=True, work_from_home=True, age_min=25, age_max=45),
        ),
        (
            "Case C: apartment + lower income",
            AudienceFilter(home_type="Apartment", income_max=50000, household_size_max=2),
        ),
    ]

    for index, (label, audience_filter) in enumerate(cases, start=1):
        print("=" * 88)
        print(f"{index}. {label}")
        print("Audience filter:", audience_filter.model_dump())
        samples = sample_grounded_trait_bundles(
            audience_filter=audience_filter,
            priors=priors,
            n=8,
            seed=100 + index,
        )
        for sample_index, sample in enumerate(samples, start=1):
            print(f"  sample_{sample_index}: {sample}")


if __name__ == "__main__":
    main()
