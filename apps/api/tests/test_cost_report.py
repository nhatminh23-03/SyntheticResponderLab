from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from src.services.interviewer_agent import DEFAULT_INTERVIEW_TURN_LIMIT
from src.services.model_catalog import MODEL_TIERS, TIER_ORDER


TOKENS_PER_MILLION = Decimal("1000000")
MEASURED_TOKEN_PROFILES = (
    (Decimal("383"), Decimal("90"), Decimal("0.0000743")),
    (Decimal("357"), Decimal("158"), Decimal("0.00014835")),
)
EXPECTED_TIER_COSTS = {
    "cheap": {
        "turns": (Decimal("0.0000743"), Decimal("0.00014835")),
        "sessions": (Decimal("0.0005944"), Decimal("0.00118680")),
        "comparison": Decimal("0.00022265"),
        "ai_run": Decimal("0.00534360"),
        "sweeps": (Decimal("0.0713280"), Decimal("0.14241600")),
    },
    "mid": {
        "turns": (Decimal("0.0003399"), Decimal("0.001147")),
        "sessions": (Decimal("0.0027192"), Decimal("0.009176")),
        "comparison": Decimal("0.0014869"),
        "ai_run": Decimal("0.0356856"),
        "sweeps": (Decimal("0.3263040"), Decimal("1.101120")),
    },
    "expensive": {
        "turns": (Decimal("0.00137875"), Decimal("0.003441")),
        "sessions": (Decimal("0.01103000"), Decimal("0.027528")),
        "comparison": Decimal("0.00481975"),
        "ai_run": Decimal("0.11567400"),
        "sweeps": (Decimal("1.32360000"), Decimal("3.303360")),
    },
}


def cost_for_profile(model: dict[str, object], profile_index: int) -> Decimal:
    tokens_in, tokens_out, _ = MEASURED_TOKEN_PROFILES[profile_index]
    return (
        tokens_in * Decimal(str(model["prompt_price_per_million"]))
        + tokens_out * Decimal(str(model["completion_price_per_million"]))
    ) / TOKENS_PER_MILLION


def test_cost_report_calculations_use_measured_profiles_and_catalog_rates():
    assert DEFAULT_INTERVIEW_TURN_LIMIT == 8
    assert 30 * 32 == 960

    for tier in TIER_ORDER:
        models = MODEL_TIERS[tier]
        turn_costs = tuple(
            cost_for_profile(model, index) for index, model in enumerate(models)
        )
        expected = EXPECTED_TIER_COSTS[tier]

        assert turn_costs == expected["turns"]
        assert tuple(cost * 8 for cost in turn_costs) == expected["sessions"]
        assert sum(turn_costs) == expected["comparison"]
        assert sum(turn_costs) * 3 * 8 == expected["ai_run"]
        assert tuple(cost * 960 for cost in turn_costs) == expected["sweeps"]

    measured_costs = tuple(profile[2] for profile in MEASURED_TOKEN_PROFILES)
    assert EXPECTED_TIER_COSTS["cheap"]["turns"] == measured_costs
    assert sum(measured_costs) == Decimal("0.00022265")
    assert measured_costs[0] * 30 * 4 == Decimal("0.0089160")
    assert measured_costs[0] * 119 == Decimal("0.0088417")


def test_cost_report_publishes_the_checked_totals_and_measurement_labels():
    report = (
        Path(__file__).resolve().parents[3] / "docs" / "cost-report.md"
    ).read_text(encoding="utf-8")

    for required_text in (
        "**Status: P3.4 is not complete.**",
        "No complete eight-turn interview or full run has been measured",
        "$0.00022265 measured",
        "$0.00534360",
        "$0.03568560",
        "$0.11567400",
        "$0.213744",
        "$1.427424",
        "$4.626960",
        "$0.008916 one-time cold-cache extrapolation",
        "**Measured:**",
        "**Extrapolated:**",
    ):
        assert required_text in report
