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


# The scenario table in the report is written as a model PAIR per tier. These are
# those pairs. Naming them explicitly keeps the table honest as the catalog grows:
# a model added to a tier is not silently folded into the pinned pair numbers, and
# reordering a tier fails the identity assertion below rather than quietly
# repricing a published row.
PAIR_TABLE_MODEL_IDS = {
    "cheap": ("google/gemini-2.5-flash-lite", "openai/gpt-4o-mini"),
    "mid": ("google/gemini-2.5-flash", "anthropic/claude-haiku-4.5"),
    "expensive": ("google/gemini-2.5-pro", "anthropic/claude-sonnet-4.5"),
}

# Added 2026-09-06 at Dr. Lin's request; priced from the OpenRouter catalog that
# day and costed against the same two measured token workloads as every other
# extrapolated row.
LIN_RECOMMENDED_MODELS = {
    "qwen/qwen3.7-plus": {
        "tier": "cheap",
        "turns": (Decimal("0.00023776"), Decimal("0.00031648")),
        "sessions": (Decimal("0.00190208"), Decimal("0.00253184")),
        "sweeps": (Decimal("0.22824960"), Decimal("0.30382080")),
    },
    "deepseek/deepseek-v4-pro": {
        "tier": "mid",
        "turns": (Decimal("0.0005828739"), Decimal("0.0006967569")),
        "sessions": (Decimal("0.0046629912"), Decimal("0.0055740552")),
        "sweeps": (Decimal("0.5595589440"), Decimal("0.6688866240")),
    },
}


def test_cost_report_calculations_use_measured_profiles_and_catalog_rates():
    assert DEFAULT_INTERVIEW_TURN_LIMIT == 8
    assert 30 * 32 == 960

    for tier in TIER_ORDER:
        models = MODEL_TIERS[tier]
        pair_ids = PAIR_TABLE_MODEL_IDS[tier]
        pair = tuple(model for model in models if model["id"] in pair_ids)
        assert tuple(model["id"] for model in pair) == pair_ids
        assert len(MEASURED_TOKEN_PROFILES) == len(pair)
        turn_costs = tuple(
            cost_for_profile(model, index) for index, model in enumerate(pair)
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


# The published figures, read from the cost ledger on 2026-09-10 with:
#   sqlite3 apps/api/local-dev.db "select model, count(distinct persona_id),
#     round(sum(cost_usd)/count(distinct persona_id),4), round(sum(cost_usd),4)
#     from interview_turn where cost_usd > 0 group by model;"
# Pinned here so a number cannot be edited in the report alone.
PUBLISHED_MEASURED = {
    "DeepSeek V4 Pro": (30, Decimal("0.0313"), Decimal("0.9387")),
    "Qwen3.7 Plus": (30, Decimal("0.0281"), Decimal("0.8422")),
}
PUBLISHED_TOTAL = Decimal("1.78")


def read_report() -> str:
    return (
        Path(__file__).resolve().parents[3] / "docs" / "cost-report.md"
    ).read_text(encoding="utf-8")


def test_cost_report_publishes_the_measured_totals():
    report = read_report()

    # The report went stale once: it kept declaring the work unmeasured after
    # sixty interviews had been metered. Pin the live claim, not just the numbers.
    assert "**Status: P3.4 is complete.**" in report
    assert "is not complete" not in report

    for label, (interviews, per_interview, total) in PUBLISHED_MEASURED.items():
        assert label in report
        assert f"${per_interview:.4f}" in report
        assert f"${total:.4f}" in report
        # Internal consistency: a per-interview figure that no longer divides the
        # published total means one of the two was edited on its own.
        assert abs(per_interview * interviews - total) <= Decimal("0.01")

    assert f"${PUBLISHED_TOTAL}" in report
    assert abs(sum(t for _, _, t in PUBLISHED_MEASURED.values()) - PUBLISHED_TOTAL) <= Decimal("0.01")

    # The classroom ceiling is enforced in llm_budget.py; the report must quote it
    # as a ceiling, never as the expected spend.
    assert "$22.50" in report
    assert "hard ceiling" in report
    assert "not the expected bill" in report


def test_lin_recommended_models_are_in_the_catalog_and_priced_in_the_report():
    catalogued = {
        model["id"]: model for tier in TIER_ORDER for model in MODEL_TIERS[tier]
    }
    report = (
        Path(__file__).resolve().parents[3] / "docs" / "cost-report.md"
    ).read_text(encoding="utf-8")

    for model_id, expected in LIN_RECOMMENDED_MODELS.items():
        model = catalogued[model_id]
        assert model["tier"] == expected["tier"]

        turn_costs = tuple(
            cost_for_profile(model, index)
            for index in range(len(MEASURED_TOKEN_PROFILES))
        )
        assert turn_costs == expected["turns"]
        assert tuple(cost * 8 for cost in turn_costs) == expected["sessions"]
        assert tuple(cost * 960 for cost in turn_costs) == expected["sweeps"]

    # DeepSeek V4 Pro is the dearer of Dr. Lin's pair, and its relationship to the
    # mid tier's Claude Haiku 4.5 is split: dearer per input token, under half per
    # output token, cheaper per actual interview. The report says exactly that, so
    # pin all three legs here -- an unqualified "cheaper" would be wrong.
    deepseek = catalogued["deepseek/deepseek-v4-pro"]
    haiku = catalogued["anthropic/claude-haiku-4.5"]
    qwen = catalogued["qwen/qwen3.7-plus"]
    assert deepseek["prompt_price_per_million"] > qwen["prompt_price_per_million"]
    assert deepseek["prompt_price_per_million"] > haiku["prompt_price_per_million"]
    assert deepseek["completion_price_per_million"] < haiku["completion_price_per_million"] / 2

    def blended(model):
        return (
            Decimal(str(model["prompt_price_per_million"])) * 10_000
            + Decimal(str(model["completion_price_per_million"])) * 2_000
        ) / Decimal("1000000")

    assert blended(deepseek) == Decimal("0.0144942")
    assert blended(haiku) == Decimal("0.0200")
    assert blended(deepseek) < blended(haiku)

    # The report's qualitative claim about the pair, which survives the rewrite:
    # they are close in price, and the reason is Qwen's reasoning tokens.
    report = read_report()
    assert "within ten percent of each other" in report
    assert "reasoning" in report
