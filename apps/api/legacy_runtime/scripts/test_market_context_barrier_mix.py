from collections import Counter

from backend.schemas import (
    AudienceFilter,
    BusinessProductContext,
    CompetitorEntry,
    MarketContext,
    SimulationRunConfig,
    SurveyQuestion,
    SurveySchema,
)
from backend.simulation.persona_generator import generate_persona_profiles
from backend.simulation.run_manager import generate_mock_response_records


def count_tokens(records):
    counts = Counter()
    for record in records:
        if not isinstance(record.answer, list):
            continue
        for answer in record.answer:
            low = answer.lower()
            if "cost" in low:
                counts["cost"] += 1
            if "install" in low or "setup" in low:
                counts["install_setup"] += 1
            if "permit" in low or "permission" in low or "landlord" in low:
                counts["permits_permission"] += 1
            if "complex" in low:
                counts["complexity"] += 1
    return dict(counts)


def main():
    audience = AudienceFilter(
        state="California",
        age_min=25,
        age_max=55,
        lifestyle_tags=["Remote Worker", "Wellness Focused"],
    )
    product_context = BusinessProductContext(
        product_name="Neo Pod",
        product_type="Backyard studio office pod",
        product_description="Modular pod",
        target_customer="Remote workers",
        price_range="Premium",
        key_features=["customization"],
    )
    survey = SurveySchema(
        survey_title="AB2",
        source_format="md",
        questions=[
            SurveyQuestion(
                id="Q_B",
                text="What barriers do you expect?",
                question_type="multi_choice",
                options=[
                    "Cost",
                    "Installation complexity",
                    "Permits/landlord permission",
                    "Space constraints",
                    "Complexity",
                    "Trust/reliability",
                ],
            ),
        ],
    )
    cfg = SimulationRunConfig(
        run_id="AB2",
        survey_title="AB2",
        survey_question_count=1,
        sample_size=48,
        selected_models=["GPT", "Gemini"],
        experiment_mode="split",
        reruns_per_persona=1,
        status="pending",
    )
    personas = generate_persona_profiles(audience_filter=audience, sample_size=48)

    market_a = MarketContext(
        category="backyard studio / office pod",
        typical_price_band="premium",
        common_expected_features=["turnkey install", "warranty", "customization"],
        common_objections=["permits", "installation", "cost"],
        substitutes=["remodel", "shed conversion"],
    )
    market_b = MarketContext(
        category="backyard studio / office pod",
        typical_price_band="low to mid",
        substitutes=["cheap shed conversion", "used office pod", "coworking membership"],
        common_objections=["cost", "complexity", "setup hassle"],
        common_expected_features=["low cost", "simple setup"],
        direct_competitors=[
            CompetitorEntry(
                name="BudgetPods",
                key_features=["cheap", "simple setup"],
                strengths=["low price", "easy setup"],
            )
        ],
    )

    recs_a = generate_mock_response_records(
        cfg,
        survey,
        audience_filter=audience,
        persona_profiles=personas,
        business_product_context=product_context,
        market_context=market_a,
    )
    recs_b = generate_mock_response_records(
        cfg,
        survey,
        audience_filter=audience,
        persona_profiles=personas,
        business_product_context=product_context,
        market_context=market_b,
    )

    print("A_multi_barrier_token_counts", count_tokens(recs_a))
    print("B_multi_barrier_token_counts", count_tokens(recs_b))


if __name__ == "__main__":
    main()
