from __future__ import annotations

from src.adapters.legacy_backend.runtime import load_module


def test_persona_generator_adds_ml_completion_trace(test_settings):
    schemas = load_module("backend.schemas", test_settings.legacy_app_root)
    persona_generator = load_module("backend.simulation.persona_generator", test_settings.legacy_app_root)
    prompt_builder = load_module("backend.simulation.prompt_builder", test_settings.legacy_app_root)

    personas, mode = persona_generator.generate_persona_profiles_with_mode(
        audience_filter=schemas.AudienceFilter(
            state="California",
            zip_code="94105",
            age_min=30,
            age_max=55,
            homeowner_only=True,
        ),
        sample_size=1,
        use_grounded_priors=False,
        geography_context=schemas.GeographyContext(zip_code="94105", puma="7301.0", cbsa_code="41860"),
    )

    assert mode == "heuristic_only"
    persona = personas[0]
    assert persona.ml_inference is not None
    assert persona.ml_inference["method"] == "weighted_tabular_bayes_v1"
    assert "affordability_pressure" in persona.ml_inference["predicted_traits"]
    assert persona.household_size_bucket is not None
    assert persona.affordability_pressure is not None

    prompt_payload = prompt_builder.build_openrouter_prompt_payload(
        persona=persona,
        survey_schema=schemas.SurveySchema(
            survey_title="Prompt ML Test",
            questions=[
                schemas.SurveyQuestion(
                    id="Q1",
                    text="What do you think?",
                    question_type="open_text",
                )
            ],
        ),
        business_product_context=None,
        market_context=None,
        audience_filter=schemas.AudienceFilter(state="California"),
    )

    user_prompt = prompt_payload["messages"][1]["content"]
    assert "CONTEXT_JSON" not in user_prompt
    assert "Persona" in user_prompt
    assert "Business and product context" in user_prompt
    assert "Survey" in user_prompt
    assert "ml_inference" not in user_prompt


def test_grounded_persona_generation_reports_ml_completion_note(test_settings):
    schemas = load_module("backend.schemas", test_settings.legacy_app_root)
    persona_generator = load_module("backend.simulation.persona_generator", test_settings.legacy_app_root)

    personas, mode = persona_generator.generate_persona_profiles_with_mode(
        audience_filter=schemas.AudienceFilter(
            state="California",
            zip_code="94105",
            age_min=30,
            age_max=55,
            homeowner_only=True,
        ),
        sample_size=1,
        use_grounded_priors=True,
        geography_context=schemas.GeographyContext(zip_code="94105", puma="7301.0", cbsa_code="41860"),
    )

    assert mode == "grounded_priors"
    assert personas[0].ml_inference is not None
    notes = persona_generator.get_last_persona_prior_notes()
    assert any(note.get("prior_table_name") == "ml_persona_completion" for note in notes)


def test_prompt_builder_returns_human_readable_preview(test_settings):
    schemas = load_module("backend.schemas", test_settings.legacy_app_root)
    prompt_builder = load_module("backend.simulation.prompt_builder", test_settings.legacy_app_root)

    persona = schemas.PersonaProfile(
        persona_id="PERS_001",
        segment_label="Remote Professionals",
        fit_tier="high",
        age_bucket="30-39",
        income_bucket="$100k-$149k",
        ownership="owner",
        home_type="Single-family",
        work_mode="remote",
        likely_use_case="Home office",
        likely_barrier="Cost",
    )
    preview = prompt_builder.build_openrouter_prompt_preview(
        persona=persona,
        survey_schema=schemas.SurveySchema(
            survey_title="Prompt Preview Test",
            description="Test survey",
            questions=[
                schemas.SurveyQuestion(
                    id="Q1",
                    text="How interested are you?",
                    question_type="likert",
                    min_value=1,
                    max_value=5,
                )
            ],
        ),
        business_product_context=schemas.BusinessProductContext(
            business_name="Neo Smart Living",
            product_name="Tahoe Mini",
            product_type="Backyard studio",
        ),
        market_context=schemas.MarketContext(
            category="Backyard prefab studio",
            substitutes=["ADU conversion"],
        ),
        audience_filter=schemas.AudienceFilter(
            state="California",
            zip_code="94105",
            age_min=30,
            age_max=55,
        ),
    )

    assert "System\n" in preview["combined_prompt"]
    assert "User\n" in preview["combined_prompt"]
    assert "You are acting as this grounded persona." in preview["user_instruction"]
    assert "Persona ID: PERS_001" in preview["user_instruction"]
    assert "Product: Tahoe Mini" in preview["user_instruction"]
    assert "Category: Backyard prefab studio" in preview["user_instruction"]
    assert "Q1 [likert] How interested are you?" in preview["user_instruction"]
