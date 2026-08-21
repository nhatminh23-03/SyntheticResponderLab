from collections import Counter, defaultdict
from statistics import mean

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


def summarize(records, personas, label):
    by_q = defaultdict(list)
    for r in records:
        by_q[r.question_id].append(r)

    adoption_vals = [r.answer for r in by_q["Q_ADOPT"] if isinstance(r.answer, int)]
    feasibility_vals = [r.answer for r in by_q["Q_FEAS"] if isinstance(r.answer, int)]
    barrier_answers = [str(r.answer) for r in by_q["Q_BARRIER"]]
    barrier_counts = Counter(barrier_answers)

    ownership_by_resp = {}
    income_by_resp = {}
    respondent_count = len({r.respondent_id for r in records})
    for idx in range(1, respondent_count + 1):
        p = personas[(idx - 1) % len(personas)]
        ownership_by_resp[f"RESP_{idx:03d}"] = p.ownership or ""
        income_by_resp[f"RESP_{idx:03d}"] = p.income_bucket or ""

    feas_owner = []
    feas_renter = []
    for r in by_q["Q_FEAS"]:
        if not isinstance(r.answer, int):
            continue
        own = ownership_by_resp.get(r.respondent_id, "")
        if own == "owner":
            feas_owner.append(r.answer)
        elif own == "renter":
            feas_renter.append(r.answer)

    low_income_cost_barriers = 0
    low_income_total = 0
    high_income_cost_barriers = 0
    high_income_total = 0
    for r in by_q["Q_BARRIER"]:
        inc = income_by_resp.get(r.respondent_id, "")
        ans = str(r.answer).lower()
        if inc == "low":
            low_income_total += 1
            if "cost" in ans or "budget" in ans or "price" in ans:
                low_income_cost_barriers += 1
        if inc == "high":
            high_income_total += 1
            if "cost" in ans or "budget" in ans or "price" in ans:
                high_income_cost_barriers += 1

    caution_mentions = sum(
        1
        for r in by_q["Q_OPEN"]
        if isinstance(r.answer, str)
        and (
            "alternatives seem easier or cheaper" in r.answer.lower()
            or "compare this with alternatives" in r.answer.lower()
            or "cautious" in r.answer.lower()
        )
    )

    return {
        "label": label,
        "adoption_mean": round(mean(adoption_vals), 3),
        "feasibility_mean": round(mean(feasibility_vals), 3),
        "barrier_counts": dict(barrier_counts),
        "top_barriers": barrier_counts.most_common(3),
        "feas_owner_mean": round(mean(feas_owner), 3) if feas_owner else None,
        "feas_renter_mean": round(mean(feas_renter), 3) if feas_renter else None,
        "low_income_cost_barrier_rate": round(low_income_cost_barriers / low_income_total, 3) if low_income_total else None,
        "high_income_cost_barrier_rate": round(high_income_cost_barriers / high_income_total, 3) if high_income_total else None,
        "relative_value_caution_mentions": caution_mentions,
    }


def main():
    audience = AudienceFilter(
        state="California",
        age_min=25,
        age_max=55,
        lifestyle_tags=["Remote Worker", "Wellness Focused"],
    )

    product_context = BusinessProductContext(
        business_name="Neo Smart Living",
        industry="Home Improvement",
        product_name="Neo Pod",
        product_type="Backyard studio office pod",
        product_description="Modular backyard pod for focused work and flexible use",
        target_customer="Remote workers and hybrid professionals",
        price_range="Premium",
        primary_goal="Increase adoption among homeowners and qualified renters",
        key_features=["modular design", "customization options"],
        main_use_cases=["home office", "creative studio"],
        main_pain_points_solved=["work-life separation", "productivity"],
        main_barriers_or_concerns=["installation complexity", "upfront cost"],
    )

    survey = SurveySchema(
        survey_title="Market Influence A/B",
        source_format="md",
        questions=[
            SurveyQuestion(
                id="Q_ADOPT",
                text="How likely are you to adopt this solution?",
                question_type="likert",
                min_value=1,
                max_value=5,
            ),
            SurveyQuestion(
                id="Q_FEAS",
                text="How feasible is this for your home situation?",
                question_type="likert",
                min_value=1,
                max_value=5,
            ),
            SurveyQuestion(
                id="Q_BARRIER",
                text="What is your primary barrier?",
                question_type="single_choice",
                options=[
                    "Cost",
                    "Installation complexity",
                    "Permits/HOA/landlord permission",
                    "Space constraints",
                    "Trust/reliability",
                    "No major concerns",
                ],
            ),
            SurveyQuestion(
                id="Q_OPEN",
                text="Any additional thoughts on value versus alternatives?",
                question_type="open_text",
            ),
        ],
    )

    cfg = SimulationRunConfig(
        run_id="RUN_MARKET_AB",
        survey_title=survey.survey_title,
        survey_question_count=len(survey.questions),
        sample_size=48,
        selected_models=["GPT", "Gemini"],
        experiment_mode="split",
        reruns_per_persona=1,
        status="pending",
    )

    personas = generate_persona_profiles(audience_filter=audience, sample_size=cfg.sample_size)

    market_a = MarketContext(
        category="backyard studio / office pod",
        typical_price_band="premium",
        common_expected_features=["turnkey install", "warranty", "customization"],
        common_objections=["permits", "installation", "cost"],
        substitutes=["remodel", "shed conversion"],
        direct_competitors=[
            CompetitorEntry(
                name="PodCo",
                product_type="office pod",
                price_range="premium",
                key_features=["turnkey install", "custom options"],
                strengths=["quality build"],
                weaknesses=["high cost"],
            )
        ],
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
                product_type="used office pod",
                price_range="low",
                key_features=["cheap", "simple setup"],
                strengths=["low price", "easy setup"],
                weaknesses=["limited customization"],
            )
        ],
    )

    recs_a = generate_mock_response_records(
        config=cfg,
        survey_schema=survey,
        audience_filter=audience,
        persona_profiles=personas,
        business_product_context=product_context,
        market_context=market_a,
    )
    recs_b = generate_mock_response_records(
        config=cfg,
        survey_schema=survey,
        audience_filter=audience,
        persona_profiles=personas,
        business_product_context=product_context,
        market_context=market_b,
    )

    sum_a = summarize(recs_a, personas, "A_premium_competitive")
    sum_b = summarize(recs_b, personas, "B_price_sensitive_alternative_heavy")

    print("TEST_A", sum_a)
    print("TEST_B", sum_b)
    print(
        "CHECKS",
        {
            "B_adoption_drops": sum_b["adoption_mean"] < sum_a["adoption_mean"],
            "B_feasibility_drops": sum_b["feasibility_mean"] < sum_a["feasibility_mean"],
            "A_barriers_include_install": any("install" in k.lower() for k in sum_a["barrier_counts"]),
            "A_barriers_include_cost": any("cost" in k.lower() for k in sum_a["barrier_counts"]),
            "A_barriers_include_permits_permission": any(
                ("permit" in k.lower()) or ("permission" in k.lower()) for k in sum_a["barrier_counts"]
            ),
            "A_owner_vs_renter_feas_gap": (sum_a["feas_owner_mean"] or 0) > (sum_a["feas_renter_mean"] or 0),
            "B_low_income_more_cost_sensitive": (sum_b["low_income_cost_barrier_rate"] or 0)
            >= (sum_b["high_income_cost_barrier_rate"] or 0),
            "B_relative_value_caution_higher": sum_b["relative_value_caution_mentions"]
            >= sum_a["relative_value_caution_mentions"],
        },
    )


if __name__ == "__main__":
    main()
