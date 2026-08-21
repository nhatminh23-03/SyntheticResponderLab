from __future__ import annotations

import pandas as pd

from backend.schemas import (
    AudienceFilter,
    BusinessProductContext,
    MarketContext,
    SurveySchema,
    SurveyQuestion,
    SimulationRunConfig,
)
from backend.grounding.prior_sampler import load_grounding_priors, sample_grounded_trait_bundles
from backend.simulation.persona_generator import (
    generate_persona_profiles_with_mode,
    _build_profiles_from_grounded_bundles,
)
from backend.simulation.run_manager import generate_mock_response_records


def build_survey() -> SurveySchema:
    return SurveySchema(
        survey_title="Affordability Reality Check",
        source_format="md",
        questions=[
            SurveyQuestion(
                id="Q_USE",
                text="What is your primary use case?",
                question_type="single_choice",
                options=["Home office", "Wellness studio", "Storage optimization", "Guest-ready space"],
            ),
            SurveyQuestion(
                id="Q_BAR",
                text="What is your top barrier or concern?",
                question_type="single_choice",
                options=["Cost", "Space", "Installation complexity", "Permission/landlord rules"],
            ),
            SurveyQuestion(
                id="Q_ADOPT",
                text="How likely are you to adopt this product in the next 6 months?",
                question_type="single_choice",
                options=["Very likely", "Likely", "Maybe", "Unlikely"],
            ),
            SurveyQuestion(
                id="Q_FEAS",
                text="How feasible is this product for your household right now?",
                question_type="likert",
                min_value=1,
                max_value=5,
            ),
        ],
    )


def metrics_from_run(personas, records):
    personas_df = pd.DataFrame([p.model_dump() for p in personas])
    records_df = pd.DataFrame([r.model_dump() for r in records])

    def ratio(series, value):
        if len(series) == 0:
            return 0.0
        return float((series == value).mean())

    pressure_high = ratio(personas_df.get("affordability_pressure", pd.Series(dtype="string")), "high_pressure")
    burden_high = ratio(personas_df.get("housing_burden_proxy", pd.Series(dtype="string")), "high")

    qbar = records_df[records_df["question_id"] == "Q_BAR"]["answer"].astype(str)
    cost_share = ratio(qbar, "Cost")

    qadopt = records_df[records_df["question_id"] == "Q_ADOPT"]["answer"].astype(str)
    positive_share = float(qadopt.isin(["Very likely", "Likely"]).mean()) if len(qadopt) else 0.0
    cautious_share = float(qadopt.isin(["Maybe", "Unlikely"]).mean()) if len(qadopt) else 0.0

    qfeas = pd.to_numeric(records_df[records_df["question_id"] == "Q_FEAS"]["answer"], errors="coerce")
    feas_mean = float(qfeas.mean()) if qfeas.notna().any() else 0.0

    return {
        "pressure_high_share": round(pressure_high, 4),
        "housing_burden_high_share": round(burden_high, 4),
        "cost_barrier_share": round(cost_share, 4),
        "adoption_positive_share": round(positive_share, 4),
        "adoption_cautious_share": round(cautious_share, 4),
        "feasibility_mean": round(feas_mean, 4),
    }


def run_scenario(label, audience_filter, business_context, market_context, sample_size=260):
    survey = build_survey()
    cfg = SimulationRunConfig(
        run_id=f"TEST_{label}",
        survey_title=survey.survey_title,
        survey_question_count=len(survey.questions),
        sample_size=sample_size,
        selected_models=["GPT", "Gemini"],
        experiment_mode="split",
        reruns_per_persona=1,
        status="pending",
    )

    personas_after, mode = generate_persona_profiles_with_mode(
        audience_filter=audience_filter,
        sample_size=sample_size,
        use_grounded_priors=True,
        seed=11,
    )
    records_after = generate_mock_response_records(
        config=cfg,
        survey_schema=survey,
        audience_filter=audience_filter,
        persona_profiles=personas_after,
        business_product_context=business_context,
        market_context=market_context,
    )

    priors = load_grounding_priors()
    priors.pop("cex_affordability", None)
    priors.pop("cex_spending", None)
    bundles_no_cex = sample_grounded_trait_bundles(
        audience_filter=audience_filter,
        priors=priors,
        n=sample_size,
        seed=11,
    )
    personas_before = _build_profiles_from_grounded_bundles(audience_filter, bundles_no_cex)
    records_before = generate_mock_response_records(
        config=cfg,
        survey_schema=survey,
        audience_filter=audience_filter,
        persona_profiles=personas_before,
        business_product_context=business_context,
        market_context=market_context,
    )

    return {
        "mode": mode,
        "after": metrics_from_run(personas_after, records_after),
        "before_proxy": metrics_from_run(personas_before, records_before),
    }


def main():
    test_a_audience = AudienceFilter(state="California", renter_only=True, income_max=60000)
    test_a_business = BusinessProductContext(
        product_name="NeoPod",
        product_type="smart backyard pod",
        product_description="Premium modular pod with smart controls and installation package.",
        price_range="$18,000-$24,000",
        target_customer="budget conscious renters",
        key_features=["smart climate", "modular", "home office"],
        main_use_cases=["home office", "focus room"],
        main_pain_points_solved=["workspace shortage"],
        main_barriers_or_concerns=["cost", "installation"],
    )
    test_a_market = MarketContext(
        category="backyard pods",
        substitutes=["cheap DIY shed", "portable office setup"],
        typical_price_band="budget and low cost market",
        common_expected_features=["easy setup", "affordable monthly payments"],
        common_objections=["cost", "budget", "price", "landlord permission"],
    )

    test_b_audience = AudienceFilter(state="California", homeowner_only=True, income_min=90000)
    test_b_business = BusinessProductContext(
        product_name="NeoPod Premium",
        product_type="premium smart backyard pod",
        product_description="Premium turnkey pod aligned with quality-focused homeowners.",
        price_range="$14,000-$19,000",
        target_customer="homeowners, remote professionals, premium buyers",
        key_features=["turnkey install", "warranty", "financing", "home office"],
        main_use_cases=["home office", "guest-ready space"],
        main_pain_points_solved=["workspace quality", "home value enhancement"],
        main_barriers_or_concerns=["timeline"],
    )
    test_b_market = MarketContext(
        category="backyard pods",
        substitutes=["premium home addition"],
        typical_price_band="premium but aligned",
        common_expected_features=["turnkey", "warranty", "financing", "simple install"],
        common_objections=["timeline"],
    )

    a = run_scenario("A", test_a_audience, test_a_business, test_a_market)
    b = run_scenario("B", test_b_audience, test_b_business, test_b_market)

    print("TEST_A", a)
    print("TEST_B", b)

    def spread(key, block):
        return round(block["A"][key] - block["B"][key], 4)

    after_block = {"A": a["after"], "B": b["after"]}
    before_block = {"A": a["before_proxy"], "B": b["before_proxy"]}

    compare = {
        "cost_barrier_spread_after": spread("cost_barrier_share", after_block),
        "cost_barrier_spread_before": spread("cost_barrier_share", before_block),
        "adoption_positive_spread_after": spread("adoption_positive_share", after_block),
        "adoption_positive_spread_before": spread("adoption_positive_share", before_block),
        "pressure_high_spread_after": spread("pressure_high_share", after_block),
        "pressure_high_spread_before": spread("pressure_high_share", before_block),
    }
    print("TEST_C_COMPARE", compare)


if __name__ == "__main__":
    main()
