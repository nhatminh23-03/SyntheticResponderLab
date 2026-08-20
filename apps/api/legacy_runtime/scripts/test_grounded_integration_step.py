from collections import Counter
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas import AudienceFilter
from backend.simulation.persona_generator import generate_persona_profiles_with_mode


def summarize(label, profiles, mode):
    ownership = Counter((p.ownership or "unknown") for p in profiles)
    home_type = Counter((p.home_type or "unknown") for p in profiles)
    work_mode = Counter((p.work_mode or "unknown") for p in profiles)
    income = Counter((p.income_bucket or "unknown") for p in profiles)
    household = Counter((p.household_size_bucket or "unknown") for p in profiles)
    print("=" * 90)
    print(label)
    print("mode=", mode)
    print("ownership=", dict(ownership))
    print("home_type=", dict(home_type))
    print("work_mode=", dict(work_mode))
    print("income_bucket=", dict(income))
    print("household_size_bucket=", dict(household))
    print("sample_preview=", [p.model_dump() for p in profiles[:3]])


def main():
    # Test 1: homeowner only + California + WFH + moderate income
    aud1 = AudienceFilter(
        state="California",
        homeowner_only=True,
        work_from_home=True,
        income_min=50000,
        income_max=120000,
    )
    profiles1, mode1 = generate_persona_profiles_with_mode(
        audience_filter=aud1,
        sample_size=30,
        use_grounded_priors=True,
        seed=101,
    )
    summarize("TEST 1 grounded homeowner+WFH+moderate income", profiles1, mode1)

    # Test 2: renter + lower income + apartment + no WFH
    aud2 = AudienceFilter(
        renter_only=True,
        income_max=50000,
        home_type="Apartment",
        work_from_home=False,
    )
    profiles2, mode2 = generate_persona_profiles_with_mode(
        audience_filter=aud2,
        sample_size=30,
        use_grounded_priors=True,
        seed=202,
    )
    summarize("TEST 2 grounded renter+lower income+apartment+no WFH", profiles2, mode2)

    # Test 3: fallback behavior by explicit heuristic-only switch
    profiles3, mode3 = generate_persona_profiles_with_mode(
        audience_filter=aud2,
        sample_size=10,
        use_grounded_priors=False,
        seed=202,
    )
    summarize("TEST 3 fallback heuristic-only switch", profiles3, mode3)


if __name__ == "__main__":
    main()
