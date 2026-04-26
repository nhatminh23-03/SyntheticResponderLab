from __future__ import annotations

from src.adapters.legacy_backend.runtime import load_module


def test_persona_generator_heuristic_mode_stays_prompt_safe(test_settings):
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
    assert not hasattr(persona, "ml_inference")
    assert persona.persona_id == "PERS_001"
    assert persona.segment_label

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
    assert "CONTEXT_JSON" in user_prompt
    assert '"persona_profile"' in user_prompt
    assert '"business_product_context": null' in user_prompt
    assert '"survey"' in user_prompt
    assert "ml_inference" not in user_prompt


def test_grounded_persona_generation_reports_prior_notes_when_priors_load(test_settings, monkeypatch):
    schemas = load_module("backend.schemas", test_settings.legacy_app_root)
    persona_generator = load_module("backend.simulation.persona_generator", test_settings.legacy_app_root)
    monkeypatch.setattr(
        persona_generator,
        "load_grounding_priors",
        lambda **kwargs: {"age_income": object()},
    )
    monkeypatch.setattr(
        persona_generator,
        "sample_grounded_trait_bundles",
        lambda **kwargs: [
                {
                    "age_bucket": "35_44",
                    "income_bucket": "100k_149k",
                    "ownership_group": "owner",
                    "home_type_group": "single_family",
                    "work_mode_hint": "remote",
                    "household_size_bucket": "2",
                    "affordability_pressure": "low_pressure",
                    "housing_burden_proxy": "low",
                    "spend_intensity_bucket": "balanced",
                }
            ],
        )
    monkeypatch.setattr(
        persona_generator,
        "get_last_prior_loading_notes",
        lambda: [{"prior_table_name": "age_income"}],
    )

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
    assert personas[0].household_size_bucket is not None
    assert personas[0].affordability_pressure is not None
    notes = persona_generator.get_last_persona_prior_notes()
    assert any(note.get("prior_table_name") == "age_income" for note in notes)


def test_prompt_builder_returns_human_readable_preview(test_settings):
    schemas = load_module("backend.schemas", test_settings.legacy_app_root)
    prompt_builder = load_module("backend.simulation.prompt_builder", test_settings.legacy_app_root)

    persona = schemas.PersonaProfile(
        persona_id="PERS_001",
        segment_label="Remote Professionals",
        fit_tier="strong",
        age_bucket="30-39",
        income_bucket="$100k-$149k",
        ownership="owner",
        home_type="Single-family",
        work_mode="remote",
        likely_use_case="Home office",
        likely_barrier="Cost",
    )
    payload = prompt_builder.build_openrouter_prompt_payload(
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
    assert payload["messages"][0]["role"] == "system"
    assert "Return strict JSON only" in payload["messages"][0]["content"]
    assert payload["messages"][1]["role"] == "user"
    assert "CONTEXT_JSON" in payload["messages"][1]["content"]
    assert "PERS_001" in payload["messages"][1]["content"]
    assert "Tahoe Mini" in payload["messages"][1]["content"]
    assert "Backyard prefab studio" in payload["messages"][1]["content"]
    assert '"id": "Q1"' in payload["messages"][1]["content"]
