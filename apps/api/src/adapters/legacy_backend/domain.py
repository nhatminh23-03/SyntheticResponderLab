from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from pydantic import ValidationError

from src.adapters.legacy_backend.runtime import load_module, load_service_account_info, temporary_env
from src.adapters.legacy_backend.survey_docx_fallback import parse_aytm_style_docx_to_validated_schema
from src.config.settings import AppSettings
from src.services.exceptions import LegacyModuleApiError, ProviderUnavailableApiError, ValidationApiError


def validate_audience(payload: dict, legacy_root: Path) -> dict:
    schemas = load_module("backend.schemas", legacy_root)
    try:
        return schemas.AudienceFilter(**payload).model_dump()
    except ValidationError as exc:
        raise ValidationApiError("Audience validation failed.", {"errors": exc.errors()}) from exc


def validate_product(payload: dict, legacy_root: Path) -> dict:
    schemas = load_module("backend.schemas", legacy_root)
    try:
        return schemas.BusinessProductContext(**payload).model_dump()
    except ValidationError as exc:
        raise ValidationApiError("Product validation failed.", {"errors": exc.errors()}) from exc


def validate_market(payload: dict, legacy_root: Path) -> dict:
    schemas = load_module("backend.schemas", legacy_root)
    try:
        competitors = [schemas.CompetitorEntry(**entry) for entry in payload.get("direct_competitors", [])]
        normalized = dict(payload)
        normalized["direct_competitors"] = competitors
        return schemas.MarketContext(**normalized).model_dump()
    except ValidationError as exc:
        raise ValidationApiError("Market validation failed.", {"errors": exc.errors()}) from exc


def validate_experiment(payload: dict, legacy_root: Path) -> dict:
    schemas = load_module("backend.schemas", legacy_root)
    try:
        return schemas.ExperimentPlan(**payload).model_dump()
    except ValidationError as exc:
        raise ValidationApiError("Experiment validation failed.", {"errors": exc.errors()}) from exc


def list_model_catalog(*, settings: AppSettings) -> dict:
    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)
    fallback_models = [
        {
            "id": "openai/gpt-4o-mini",
            "name": "openai/gpt-4o-mini",
            "prompt_price_per_million": None,
            "completion_price_per_million": None,
        },
        {
            "id": "google/gemini-2.0-flash-001",
            "name": "google/gemini-2.0-flash-001",
            "prompt_price_per_million": None,
            "completion_price_per_million": None,
        },
    ]

    try:
        with temporary_env(
            {
                "OPENROUTER_API_KEY": settings.openrouter_api_key,
                "OPENROUTER_BASE_URL": settings.openrouter_base_url,
            }
        ):
            result = llm_client.list_openrouter_models(timeout=20)
    except Exception as exc:
        return {
            "source": "fallback",
            "models": fallback_models,
            "warning": f"Unable to load OpenRouter catalog: {exc}",
        }

    if bool(result.get("ok")) and result.get("models"):
        return {
            "source": "openrouter",
            "models": list(result.get("models") or []),
            "warning": None,
        }

    return {
        "source": "fallback",
        "models": fallback_models,
        "warning": result.get("error") or "OpenRouter model catalog unavailable.",
    }


def parse_normalize_validate_survey(file_name: str, file_bytes: bytes, legacy_root: Path) -> dict:
    parser = load_module("backend.survey.parser", legacy_root)
    normalizer = load_module("backend.survey.schema_normalizer", legacy_root)
    validator = load_module("backend.survey.validator", legacy_root)
    extension = file_name.lower().rsplit(".", maxsplit=1)[-1] if "." in file_name else ""
    try:
        raw = parser.parse_uploaded_survey(file_name=file_name, file_bytes=file_bytes)
        normalized = normalizer.normalize_survey_payload(raw)
        validated = validator.validate_survey_schema(normalized)
        return validated.model_dump()
    except ValueError as exc:
        if extension == "docx" and "Duplicate question ids found" in str(exc):
            try:
                extracted_text = parser._extract_text_from_docx(file_bytes)
                return parse_aytm_style_docx_to_validated_schema(
                    text=extracted_text,
                    validator_module=validator,
                )
            except ValueError as fallback_exc:
                raise ValidationApiError(str(fallback_exc)) from fallback_exc
            except Exception as fallback_exc:
                raise LegacyModuleApiError(f"DOCX fallback parsing failed: {fallback_exc}") from fallback_exc
        raise ValidationApiError(str(exc)) from exc
    except Exception as exc:
        raise LegacyModuleApiError(f"Survey parsing failed: {exc}") from exc


def load_neo_survey_schema_default(legacy_root: Path) -> tuple[str, bytes, dict]:
    presets = load_module("backend.presets", legacy_root)
    try:
        survey_path = presets.get_neo_survey_markdown_path()
        schema = presets.get_neo_survey_schema_default()
        return survey_path.name, survey_path.read_bytes(), schema.model_dump()
    except ValueError as exc:
        raise ValidationApiError(str(exc)) from exc
    except Exception as exc:
        raise LegacyModuleApiError(f"Neo survey preset load failed: {exc}") from exc


def build_geography_context(zip_code: str, settings: AppSettings) -> dict:
    geography = load_module("backend.grounding.geography_context", settings.legacy_app_root)
    try:
        context = geography.build_geography_context_from_zip(zip_code=zip_code, token=settings.hud_api_token, prefer_local=True)
        return context.model_dump()
    except Exception as exc:
        raise LegacyModuleApiError(f"Geography lookup failed: {exc}") from exc


def preview_personas(
    *,
    settings: AppSettings,
    audience_payload: dict,
    sample_size: int,
    use_grounded_priors: bool,
    use_geography_filtered_priors: bool,
    use_cex_affordability_priors: bool,
    seed: Optional[int],
    geography_context: Optional[Dict[str, Any]],
) -> dict:
    schemas = load_module("backend.schemas", settings.legacy_app_root)
    persona_generator = load_module("backend.simulation.persona_generator", settings.legacy_app_root)
    prior_sampler = load_module("backend.grounding.prior_sampler", settings.legacy_app_root)

    audience = schemas.AudienceFilter(**audience_payload)
    geography = schemas.GeographyContext(**geography_context) if geography_context else None

    try:
        grounded_available = bool(persona_generator.grounded_priors_available())
    except Exception:
        grounded_available = False

    try:
        affordability_available = bool(prior_sampler.cex_affordability_priors_available())
    except Exception:
        affordability_available = False

    try:
        personas, generation_mode = persona_generator.generate_persona_profiles_with_mode(
            audience_filter=audience,
            sample_size=sample_size,
            use_grounded_priors=use_grounded_priors,
            seed=seed,
            geography_context=geography,
            use_geography_filtered_priors=use_geography_filtered_priors,
            use_cex_affordability_priors=use_cex_affordability_priors,
        )
        prior_notes = list(persona_generator.get_last_persona_prior_notes())
    except Exception as exc:
        raise LegacyModuleApiError(f"Persona preview failed: {exc}") from exc

    return {
        "generation_mode": generation_mode,
        "grounded_priors_available": grounded_available,
        "cex_affordability_available": affordability_available,
        "prior_notes": prior_notes,
        "personas": [persona.model_dump() for persona in personas],
    }


def execute_simulation_run(
    *,
    settings: AppSettings,
    audience_payload: dict,
    survey_payload: dict,
    experiment_payload: dict,
    product_payload: Optional[dict],
    market_payload: Optional[dict],
    geography_context: Optional[Dict[str, Any]],
) -> dict:
    schemas = load_module("backend.schemas", settings.legacy_app_root)
    run_manager = load_module("backend.simulation.run_manager", settings.legacy_app_root)
    persona_generator = load_module("backend.simulation.persona_generator", settings.legacy_app_root)
    prior_sampler = load_module("backend.grounding.prior_sampler", settings.legacy_app_root)
    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)

    audience = schemas.AudienceFilter(**audience_payload)
    survey_schema = schemas.SurveySchema(**survey_payload)
    experiment = schemas.ExperimentPlan(**experiment_payload)
    business_product_context = (
        schemas.BusinessProductContext(**product_payload) if product_payload else None
    )
    market_context = schemas.MarketContext(**market_payload) if market_payload else None
    geography = schemas.GeographyContext(**geography_context) if geography_context else None

    try:
        grounded_priors_available = bool(persona_generator.grounded_priors_available())
    except Exception:
        grounded_priors_available = False

    try:
        affordability_priors_available = bool(prior_sampler.cex_affordability_priors_available())
    except Exception:
        affordability_priors_available = False

    with temporary_env(
        {
            "OPENROUTER_API_KEY": settings.openrouter_api_key,
            "OPENROUTER_BASE_URL": settings.openrouter_base_url,
        }
    ):
        try:
            openrouter_available = bool(llm_client.openrouter_api_key_available())
        except Exception:
            openrouter_available = False

    generation_mode = "openrouter_live" if openrouter_available else "mock"
    provider_model_name = experiment.selected_models[0] if experiment.selected_models else "openai/gpt-4o-mini"
    run_id = f"RUN_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    config = schemas.SimulationRunConfig(
        run_id=run_id,
        survey_title=survey_schema.survey_title,
        survey_question_count=len(survey_schema.questions),
        sample_size=experiment.sample_size,
        selected_models=experiment.selected_models or [provider_model_name],
        experiment_mode=experiment.experiment_mode,
        reruns_per_persona=experiment.reruns_per_persona,
        status="pending",
        notes="API-triggered simulation run.",
    )

    try:
        personas, persona_generation_mode = persona_generator.generate_persona_profiles_with_mode(
            audience_filter=audience,
            sample_size=experiment.sample_size,
            use_grounded_priors=grounded_priors_available,
            geography_context=geography,
            use_geography_filtered_priors=True,
            use_cex_affordability_priors=True,
        )
        prior_notes = list(persona_generator.get_last_persona_prior_notes())
    except Exception as exc:
        raise LegacyModuleApiError(f"Simulation persona generation failed: {exc}") from exc

    try:
        with temporary_env(
            {
                "OPENROUTER_API_KEY": settings.openrouter_api_key,
                "OPENROUTER_BASE_URL": settings.openrouter_base_url,
            }
        ):
            records = run_manager.generate_mock_response_records(
                config=config,
                survey_schema=survey_schema,
                audience_filter=audience,
                persona_profiles=personas,
                business_product_context=business_product_context,
                market_context=market_context,
                generation_mode=generation_mode,
                openrouter_model_name=provider_model_name,
            )
            result = run_manager.run_mock_simulation(
                config=config,
                generation_mode=generation_mode,
                provider_model_name=provider_model_name,
            )
            generation_debug = dict(run_manager.get_last_live_generation_debug())
    except Exception as exc:
        raise LegacyModuleApiError(f"Simulation execution failed: {exc}") from exc

    warnings: List[str] = []
    if generation_mode != "openrouter_live":
        warnings.append("OpenRouter live path unavailable; used mock response generation.")
    if persona_generation_mode == "heuristic_fallback":
        warnings.append("Grounded priors unavailable; personas used heuristic fallback.")
    if geography_context and not geography_context.get("puma"):
        warnings.append("Geography context was partial; geo-aware priors may have fallen back to global tables.")
    if not geography_context and audience_payload.get("zip_code"):
        warnings.append("ZIP was provided, but geography context could not be resolved; geo-aware priors stayed global.")

    return {
        "run_id": result.run_id,
        "status": result.status,
        "total_requested_responses": result.total_requested_responses,
        "total_generated_responses": result.total_generated_responses,
        "models_used": list(result.models_used),
        "experiment_mode": result.experiment_mode,
        "survey_title": result.survey_title,
        "question_count": result.question_count,
        "notes": result.notes,
        "created_at": result.created_at,
        "generation_mode": generation_mode,
        "provider_model_name": provider_model_name if generation_mode == "openrouter_live" else None,
        "persona_generation_mode": persona_generation_mode,
        "grounded_priors_available": grounded_priors_available,
        "cex_affordability_available": affordability_priors_available,
        "geography_context": geography_context,
        "prior_notes": prior_notes,
        "warnings": warnings,
        "generation_debug": generation_debug,
        "run_conditions": {
            "context_influence": {
                "enabled": True,
                "sources": (
                    ["audience"]
                    + (["product"] if business_product_context else [])
                    + (["market"] if market_context else [])
                ),
            },
            "geography_aware_priors": {
                "status": (
                    "enabled"
                    if geography_context and geography_context.get("puma")
                    else "degraded"
                    if audience_payload.get("zip_code")
                    else "global"
                ),
                "detail": (
                    "ZIP-based geography context resolved."
                    if geography_context and geography_context.get("puma")
                    else "ZIP provided but geography context was partial or unavailable."
                    if audience_payload.get("zip_code")
                    else "No ZIP constraint; priors remain global."
                ),
            },
            "grounded_priors": {
                "status": "enabled" if grounded_priors_available else "degraded",
                "detail": (
                    "Grounded priors loaded for persona generation."
                    if grounded_priors_available
                    else "Grounded priors unavailable; heuristic fallback was used."
                ),
            },
            "affordability_priors": {
                "status": "enabled" if affordability_priors_available else "degraded",
                "detail": (
                    "CEX affordability priors were available."
                    if affordability_priors_available
                    else "Affordability priors were unavailable for this run."
                ),
            },
            "generation_mode": generation_mode,
            "selected_models": list(result.models_used),
        },
        "personas": [persona.model_dump() for persona in personas],
        "response_records": [record.model_dump() for record in records],
        "response_record_preview": [record.model_dump() for record in records[:24]],
        "survey_parse_warnings": list(survey_payload.get("parse_warnings", [])),
    }


def execute_stability_check(
    *,
    settings: AppSettings,
    audience_payload: dict,
    survey_payload: dict,
    experiment_payload: dict,
    product_payload: Optional[dict],
    market_payload: Optional[dict],
    geography_context: Optional[Dict[str, Any]],
    repeat_runs: int,
) -> dict:
    if repeat_runs < 2 or repeat_runs > 5:
        raise ValidationApiError("repeat_runs must be between 2 and 5.")

    schemas = load_module("backend.schemas", settings.legacy_app_root)
    run_manager = load_module("backend.simulation.run_manager", settings.legacy_app_root)
    persona_generator = load_module("backend.simulation.persona_generator", settings.legacy_app_root)
    stability = load_module("backend.analysis.stability", settings.legacy_app_root)

    audience = schemas.AudienceFilter(**audience_payload)
    survey_schema = schemas.SurveySchema(**survey_payload)
    experiment = schemas.ExperimentPlan(**experiment_payload)
    business_product_context = (
        schemas.BusinessProductContext(**product_payload) if product_payload else None
    )
    market_context = schemas.MarketContext(**market_payload) if market_payload else None
    geography = schemas.GeographyContext(**geography_context) if geography_context else None

    try:
        grounded_priors_available = bool(persona_generator.grounded_priors_available())
    except Exception:
        grounded_priors_available = False

    run_summaries: List[dict] = []
    warnings: List[str] = [
        "Stability check uses lightweight repeated runs for repeatability signals, not formal statistical inference."
    ]
    if not grounded_priors_available:
        warnings.append("Grounded priors were unavailable during stability reruns; heuristic fallback was used.")

    for rerun_index in range(1, repeat_runs + 1):
        try:
            personas, _mode = persona_generator.generate_persona_profiles_with_mode(
                audience_filter=audience,
                sample_size=experiment.sample_size,
                use_grounded_priors=grounded_priors_available,
                geography_context=geography,
                use_geography_filtered_priors=True,
                use_cex_affordability_priors=True,
            )
        except Exception as exc:
            raise LegacyModuleApiError(f"Stability persona generation failed: {exc}") from exc

        config = schemas.SimulationRunConfig(
            run_id=f"STABILITY_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{rerun_index}",
            survey_title=survey_schema.survey_title,
            survey_question_count=len(survey_schema.questions),
            sample_size=experiment.sample_size,
            selected_models=experiment.selected_models,
            experiment_mode=experiment.experiment_mode,
            reruns_per_persona=experiment.reruns_per_persona,
            status="pending",
            notes="API-triggered stability check.",
        )

        try:
            records = run_manager.generate_mock_response_records(
                config=config,
                survey_schema=survey_schema,
                audience_filter=audience,
                persona_profiles=personas,
                business_product_context=business_product_context,
                market_context=market_context,
            )
            run_summaries.append(
                stability.summarize_run_outputs(records=records, personas=personas)
            )
        except Exception as exc:
            raise LegacyModuleApiError(f"Stability check failed: {exc}") from exc

    stability_df = stability.build_stability_table(run_summaries)
    stability_table = (
        []
        if getattr(stability_df, "empty", True)
        else stability_df.where(stability_df.notnull(), None).to_dict(orient="records")
    )
    stability_labels = [str(row.get("stability_label")) for row in stability_table if row.get("stability_label")]

    return {
        "repeat_runs": repeat_runs,
        "run_summaries": run_summaries,
        "stability_table": stability_table,
        "stability_labels": stability_labels,
        "warnings": warnings,
        "used_grounded_priors": grounded_priors_available,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def build_analysis_view(
    *,
    settings: AppSettings,
    study_mode: Optional[str],
    latest_run_payload: Optional[Dict[str, Any]],
    question_id: Optional[str],
    model: Optional[str],
    segment: Optional[str],
    records_limit: int,
    records_offset: int,
    open_text_limit: int,
) -> dict:
    transparency_note = (
        "Transparency note: Confidence and agreement labels are rule-based heuristics for demo trust framing. "
        "Use outputs for hypothesis generation and validate with real respondents."
    )

    if not latest_run_payload:
        return {
            "available": False,
            "message": "No saved simulation result is available yet. Complete Run Simulation first.",
            "transparency_note": transparency_note,
        }

    records = list(latest_run_payload.get("response_records") or [])
    personas = list(latest_run_payload.get("personas") or [])
    if not records:
        return {
            "available": False,
            "message": "The latest run does not include response records yet.",
            "transparency_note": transparency_note,
        }

    findings = load_module("backend.analysis.findings", settings.legacy_app_root)
    benchmark = load_module("backend.analysis.benchmark", settings.legacy_app_root)
    realism = load_module("backend.analysis.realism", settings.legacy_app_root)
    stability = load_module("backend.analysis.stability", settings.legacy_app_root)

    df = pd.DataFrame(records)
    summary = _compute_dataset_summary(df)
    model_options = ["All", *_list_models(df)]
    segment_options = ["All", *_list_segments(df)]
    question_options = _build_question_options(df)

    selected_model = model if model in model_options else "All"
    selected_segment = segment if segment in segment_options else "All"
    filtered_df = _apply_record_filters(df=df, model=selected_model, segment_label=selected_segment)

    selected_question_id = _resolve_selected_question_id(
        question_id=question_id,
        filtered_df=filtered_df,
        all_question_options=question_options,
    )
    question_df = (
        filtered_df[filtered_df["question_id"].astype(str) == selected_question_id].copy()
        if selected_question_id and not filtered_df.empty and "question_id" in filtered_df.columns
        else pd.DataFrame()
    )

    distribution = (
        _compute_question_answer_distribution(filtered_df, selected_question_id)
        if selected_question_id
        else pd.DataFrame(columns=["answer_display", "count", "percentage"])
    )
    trust = (
        findings.assess_question_trust(filtered_df, selected_question_id)
        if selected_question_id
        else {
            "confidence_label": "Needs validation",
            "agreement_label": "Partial agreement",
            "explanation": "No question selected yet.",
        }
    )
    question_finding = (
        (findings.build_question_findings(question_df) or [None])[0]
        if not question_df.empty
        else None
    )

    open_text_options = _build_open_text_options(filtered_df)
    selected_open_text_question_id = _resolve_open_text_question_id(
        open_text_question_id=question_id if _question_is_open_text(question_df) else None,
        open_text_options=open_text_options,
    )
    open_text_samples_df = (
        _get_example_open_text_responses(
            filtered_df,
            selected_open_text_question_id,
            limit=open_text_limit,
        )
        if selected_open_text_question_id
        else pd.DataFrame(columns=["respondent_id", "model", "segment_label", "answer"])
    )

    preview_df = filtered_df.iloc[records_offset : records_offset + records_limit].copy()
    benchmark_snapshot = _build_benchmark_snapshot(
        df=df,
        personas=personas,
        benchmark_module=benchmark,
        stability_module=stability,
    )
    realism_scorecard = _build_realism_scorecard(
        settings=settings,
        study_mode=study_mode,
        records=records,
        realism_module=realism,
    )

    return {
        "available": True,
        "transparency_note": transparency_note,
        "run": {
            "run_id": latest_run_payload.get("run_id"),
            "status": latest_run_payload.get("status"),
            "survey_title": latest_run_payload.get("survey_title"),
            "experiment_mode": latest_run_payload.get("experiment_mode"),
            "created_at": latest_run_payload.get("created_at"),
            "models_used": list(latest_run_payload.get("models_used") or []),
            "requested_responses": latest_run_payload.get("total_requested_responses"),
            "generated_responses": latest_run_payload.get("total_generated_responses"),
        },
        "summary": {
            **summary,
            "active_segment_summary": _build_active_segment_summary(summary.get("segments_present")),
        },
        "filters": {
            "question_options": question_options,
            "model_options": model_options,
            "segment_options": segment_options,
            "selected_question_id": selected_question_id,
            "selected_model": selected_model,
            "selected_segment": selected_segment,
            "filtered_record_count": int(len(filtered_df)),
        },
        "benchmark_snapshot": benchmark_snapshot,
        "realism_scorecard": realism_scorecard,
        "question_explorer": {
            "question_id": selected_question_id,
            "question_text": _safe_first_value(question_df, "question_text"),
            "question_type": _safe_first_value(question_df, "question_type"),
            "response_count": int(len(question_df)),
            "trust": trust,
            "distribution": _dataframe_to_records(distribution),
            "stats_summary": question_finding,
        },
        "open_text": {
            "available": len(open_text_options) > 0,
            "question_options": open_text_options,
            "selected_question_id": selected_open_text_question_id,
            "samples": _dataframe_to_records(open_text_samples_df),
        },
        "records_preview": {
            "total": int(len(filtered_df)),
            "offset": int(records_offset),
            "limit": int(records_limit),
            "rows": _dataframe_to_records(preview_df),
        },
        "context_notes": {
            "run_warnings": list(latest_run_payload.get("warnings") or []),
            "survey_parse_warnings": list(latest_run_payload.get("survey_parse_warnings") or []),
        },
    }


def build_insights_view(
    *,
    settings: AppSettings,
    study_mode: Optional[str],
    latest_run_payload: Optional[Dict[str, Any]],
) -> dict:
    transparency_note = (
        "Transparency note: Findings, confidence labels, and agreement labels are deterministic rule-based "
        "summaries for demo trust framing. They are exploratory and should be validated with real respondents."
    )

    if not latest_run_payload:
        return {
            "available": False,
            "message": "No saved simulation result is available yet. Complete Run Simulation first.",
            "transparency_note": transparency_note,
        }

    records = list(latest_run_payload.get("response_records") or [])
    personas = list(latest_run_payload.get("personas") or [])
    if not records:
        return {
            "available": False,
            "message": "The latest run does not include response records yet.",
            "transparency_note": transparency_note,
        }

    findings = load_module("backend.analysis.findings", settings.legacy_app_root)
    benchmark = load_module("backend.analysis.benchmark", settings.legacy_app_root)
    realism = load_module("backend.analysis.realism", settings.legacy_app_root)
    stability = load_module("backend.analysis.stability", settings.legacy_app_root)

    df = pd.DataFrame(records)
    summary = _compute_dataset_summary(df)
    question_findings = findings.build_question_findings(df)
    trust_map = findings.build_question_trust_map(df)
    model_notes = findings.build_model_comparison_notes(df)
    segment_notes = findings.build_segment_comparison_notes(df)
    recommendations = findings.build_rule_based_recommendations(
        question_findings,
        model_notes,
        segment_notes,
    )

    benchmark_snapshot = _build_benchmark_snapshot(
        df=df,
        personas=personas,
        benchmark_module=benchmark,
        stability_module=stability,
    )
    realism_scorecard = _build_realism_scorecard(
        settings=settings,
        study_mode=study_mode,
        records=records,
        realism_module=realism,
    )

    barrier_ranking = _build_barrier_ranking(df)
    message_performance = _build_message_performance(df)
    use_case_share = _build_use_case_share(df)
    interest_ladder = _build_interest_ladder(df)
    segment_heatmap = _build_segment_heatmap(df, barrier_ranking, message_performance)
    model_difference_chart = _build_model_difference_chart(df)

    executive_summary = _build_executive_summary(
        df=df,
        summary=summary,
        run_payload=latest_run_payload,
        use_case_share=use_case_share,
        model_notes=model_notes,
    )
    trust_snapshot = _build_trust_snapshot(
        trust_map=trust_map,
        benchmark_snapshot=benchmark_snapshot,
        realism_scorecard=realism_scorecard,
    )
    top_findings = _build_top_findings(
        use_case_share=use_case_share,
        barrier_ranking=barrier_ranking,
        message_performance=message_performance,
        interest_ladder=interest_ladder,
        model_difference_chart=model_difference_chart,
        trust_map=trust_map,
    )
    segment_story = _build_segment_story(
        df=df,
        segment_notes=segment_notes,
        segment_heatmap=segment_heatmap,
    )

    return {
        "available": True,
        "transparency_note": transparency_note,
        "run": {
            "run_id": latest_run_payload.get("run_id"),
            "status": latest_run_payload.get("status"),
            "survey_title": latest_run_payload.get("survey_title"),
            "experiment_mode": latest_run_payload.get("experiment_mode"),
            "created_at": latest_run_payload.get("created_at"),
            "models_used": list(latest_run_payload.get("models_used") or []),
            "requested_responses": latest_run_payload.get("total_requested_responses"),
            "generated_responses": latest_run_payload.get("total_generated_responses"),
        },
        "executive_summary": executive_summary,
        "trust_snapshot": trust_snapshot,
        "top_findings": top_findings,
        "charts": {
            "barrier_ranking": barrier_ranking,
            "message_performance": message_performance,
            "segment_heatmap": segment_heatmap,
            "use_case_share": use_case_share,
            "interest_ladder": interest_ladder,
            "model_difference": model_difference_chart,
        },
        "segment_story": segment_story,
        "recommendations": recommendations,
        "context_notes": {
            "model_notes": model_notes,
            "segment_notes": segment_notes,
            "run_warnings": list(latest_run_payload.get("warnings") or []),
            "survey_parse_warnings": list(latest_run_payload.get("survey_parse_warnings") or []),
        },
    }


def _build_question_options(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty or not {"question_id", "question_text", "question_type"}.issubset(df.columns):
        return []

    question_meta = (
        df[["question_id", "question_text", "question_type"]]
        .drop_duplicates()
        .sort_values("question_id")
    )

    options: list[dict[str, Any]] = []
    for _, row in question_meta.iterrows():
        question_id = str(row["question_id"])
        options.append(
            {
                "id": question_id,
                "text": str(row["question_text"]),
                "question_type": str(row["question_type"]),
                "response_count": int((df["question_id"].astype(str) == question_id).sum()),
            }
        )
    return options


def _compute_dataset_summary(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {
            "total_records": 0,
            "unique_respondents": 0,
            "question_count": 0,
            "models_present": [],
            "segments_present": [],
            "survey_titles_present": [],
        }

    return {
        "total_records": int(len(df)),
        "unique_respondents": int(df["respondent_id"].nunique()) if "respondent_id" in df.columns else 0,
        "question_count": int(df["question_id"].nunique()) if "question_id" in df.columns else 0,
        "models_present": _list_models(df),
        "segments_present": _list_segments(df),
        "survey_titles_present": sorted(df["survey_title"].dropna().astype(str).unique().tolist())
        if "survey_title" in df.columns
        else [],
    }


def _list_models(df: pd.DataFrame) -> list[str]:
    if df.empty or "model" not in df.columns:
        return []
    return sorted(df["model"].dropna().astype(str).unique().tolist())


def _list_segments(df: pd.DataFrame) -> list[str]:
    if df.empty or "segment_label" not in df.columns:
        return []
    return sorted(df["segment_label"].dropna().astype(str).unique().tolist())


def _apply_record_filters(df: pd.DataFrame, model: Optional[str], segment_label: Optional[str]) -> pd.DataFrame:
    if df.empty:
        return df

    filtered = df.copy()
    if model and model != "All" and "model" in filtered.columns:
        filtered = filtered[filtered["model"].astype(str) == model]
    if segment_label and segment_label != "All" and "segment_label" in filtered.columns:
        filtered = filtered[filtered["segment_label"].astype(str) == segment_label]
    return filtered


def _compute_question_answer_distribution(df: pd.DataFrame, question_id: Optional[str]) -> pd.DataFrame:
    if df.empty or not question_id or "question_id" not in df.columns:
        return pd.DataFrame(columns=["answer_display", "count", "percentage"])

    question_df = df[df["question_id"].astype(str) == question_id].copy()
    if question_df.empty:
        return pd.DataFrame(columns=["answer_display", "count", "percentage"])

    if "question_type" in question_df.columns and str(question_df["question_type"].iloc[0]) == "multi_choice":
        question_df = question_df.explode("answer")

    answer_series = question_df["answer"].apply(
        lambda value: "None" if pd.isna(value) else str(value)
    )
    counts = (
        answer_series.value_counts(dropna=False)
        .rename_axis("answer_display")
        .reset_index(name="count")
    )
    total = counts["count"].sum()
    counts["percentage"] = (counts["count"] / total * 100).round(1) if total else 0.0
    return counts


def _get_example_open_text_responses(df: pd.DataFrame, question_id: Optional[str], limit: int) -> pd.DataFrame:
    if df.empty or not question_id or "question_id" not in df.columns:
        return pd.DataFrame(columns=["respondent_id", "model", "segment_label", "answer"])

    question_df = df[df["question_id"].astype(str) == question_id].copy()
    if question_df.empty:
        return pd.DataFrame(columns=["respondent_id", "model", "segment_label", "answer"])

    columns = [
        column
        for column in ["respondent_id", "model", "segment_label", "answer"]
        if column in question_df.columns
    ]
    return question_df[columns].head(limit)


def _build_open_text_options(df: pd.DataFrame) -> list[dict[str, str]]:
    if df.empty or not {"question_id", "question_text", "question_type"}.issubset(df.columns):
        return []

    open_text_df = (
        df.loc[df["question_type"].astype(str) == "open_text", ["question_id", "question_text"]]
        .drop_duplicates()
        .sort_values("question_id")
    )
    return [
        {"id": str(row["question_id"]), "text": str(row["question_text"])}
        for _, row in open_text_df.iterrows()
    ]


def _resolve_selected_question_id(
    *,
    question_id: Optional[str],
    filtered_df: pd.DataFrame,
    all_question_options: list[dict[str, Any]],
) -> Optional[str]:
    if not filtered_df.empty and "question_id" in filtered_df.columns:
        filtered_question_ids = (
            filtered_df["question_id"].dropna().astype(str).sort_values().unique().tolist()
        )
        if question_id and question_id in filtered_question_ids:
            return question_id
        if filtered_question_ids:
            return filtered_question_ids[0]

    if question_id and any(option["id"] == question_id for option in all_question_options):
        return question_id

    return all_question_options[0]["id"] if all_question_options else None


def _resolve_open_text_question_id(
    *,
    open_text_question_id: Optional[str],
    open_text_options: list[dict[str, str]],
) -> Optional[str]:
    if open_text_question_id and any(
        option["id"] == open_text_question_id for option in open_text_options
    ):
        return open_text_question_id
    return open_text_options[0]["id"] if open_text_options else None


def _question_is_open_text(question_df: pd.DataFrame) -> bool:
    if question_df.empty or "question_type" not in question_df.columns:
        return False
    return str(question_df["question_type"].iloc[0]) == "open_text"


def _build_benchmark_snapshot(*, df: pd.DataFrame, personas: list[dict], benchmark_module: Any, stability_module: Any) -> dict:
    if df.empty or "model" not in df.columns:
        return {
            "available": False,
            "message": "No model comparison data is available for benchmark framing.",
            "detailed_table": [],
        }

    models_present = sorted(df["model"].dropna().astype(str).unique().tolist())
    if len(models_present) < 2:
        return {
            "available": False,
            "message": "Need at least two selected models in one run to compare benchmark consistency.",
            "models_compared": models_present,
            "detailed_table": [],
        }

    run_summaries: list[dict[str, Any]] = []
    for model_name in models_present:
        model_df = df[df["model"].astype(str) == model_name].copy()
        run_summaries.append(
            stability_module.summarize_run_outputs(
                records=model_df.to_dict(orient="records"),
                personas=personas,
            )
        )

    stability_df = stability_module.build_stability_table(run_summaries)
    top_use_cases = [str(item.get("top_use_case") or "n/a") for item in run_summaries]
    top_barriers = [str(item.get("top_barrier") or "n/a") for item in run_summaries]

    return {
        "available": True,
        "models_compared": models_present,
        "stability_summary": benchmark_module.summarize_stability_labels(stability_df),
        "top_use_case_consensus": Counter(top_use_cases).most_common(1)[0][0] if top_use_cases else "n/a",
        "top_barrier_consensus": Counter(top_barriers).most_common(1)[0][0] if top_barriers else "n/a",
        "detailed_table": _dataframe_to_records(stability_df),
    }


def _build_realism_scorecard(
    *,
    settings: AppSettings,
    study_mode: Optional[str],
    records: list[dict],
    realism_module: Any,
) -> dict:
    if study_mode != "neo_smart":
        return {
            "available": False,
            "message": "Realism scorecard is shown only for Neo Smart mode.",
            "summary": None,
            "question_rows": [],
        }

    targets_path = (
        Path(settings.legacy_app_root)
        / "data"
        / "processed"
        / "benchmarks"
        / "realism_targets_neo_smart_template.json"
    )
    if not targets_path.exists():
        return {
            "available": False,
            "message": "Realism targets file not found yet. Add it to enable automatic Neo realism scoring.",
            "summary": None,
            "question_rows": [],
        }

    try:
        targets_payload = realism_module.load_realism_targets_file(targets_path)
        report = realism_module.evaluate_realism_scorecard(records, targets_payload)
        question_table = report.get("question_table")
        return {
            "available": True,
            "summary": report.get("summary"),
            "question_rows": _dataframe_to_records(question_table)
            if question_table is not None
            else list(report.get("question_rows") or []),
            "message": None,
        }
    except Exception as exc:
        return {
            "available": False,
            "message": f"Realism scorecard could not be generated: {exc}",
            "summary": None,
            "question_rows": [],
        }


def _build_active_segment_summary(segments_present: Any) -> str:
    if not isinstance(segments_present, list) or not segments_present:
        return "No segment labels available"
    if len(segments_present) == 1:
        return str(segments_present[0])
    return f"{segments_present[0]}, {segments_present[1]} +{len(segments_present) - 2} more"


def _safe_first_value(df: pd.DataFrame, column: str) -> Optional[str]:
    if df.empty or column not in df.columns:
        return None
    value = df.iloc[0][column]
    if pd.isna(value):
        return None
    return str(value)


def _dataframe_to_records(df: Any) -> list[dict[str, Any]]:
    if df is None or getattr(df, "empty", True):
        return []
    return df.where(df.notnull(), None).to_dict(orient="records")


def _build_executive_summary(
    *,
    df: pd.DataFrame,
    summary: dict[str, Any],
    run_payload: dict[str, Any],
    use_case_share: dict[str, Any],
    model_notes: list[str],
) -> dict[str, Any]:
    top_use_case = "N/A"
    top_use_case_share = None
    if use_case_share.get("available") and use_case_share.get("rows"):
        top_row = use_case_share["rows"][0]
        top_use_case = str(top_row.get("label") or "N/A")
        top_use_case_share = top_row.get("share")

    average_interest = _first_question_numeric_mean(df, ["Q1", "Q0B", "Q2"])
    strongest_segment = _compute_strongest_segment(df)
    differing_questions = sum(
        1 for note in model_notes if "differences observed" in str(note).lower()
    )
    model_difference = {
        "status": (
            "Not enough model coverage"
            if len(summary.get("models_present") or []) < 2
            else "Differences observed"
            if differing_questions > 0
            else "Mostly aligned"
        ),
        "differing_questions": differing_questions,
        "note": model_notes[0] if model_notes else "No model comparison note available.",
    }

    return {
        "top_use_case": {
            "label": top_use_case,
            "share": top_use_case_share,
        },
        "average_interest": round(average_interest, 2) if average_interest is not None else None,
        "strongest_segment": strongest_segment,
        "model_difference": model_difference,
        "records_summary": {
            "total_records": summary.get("total_records"),
            "unique_respondents": summary.get("unique_respondents"),
            "questions": summary.get("question_count"),
            "survey_title": run_payload.get("survey_title"),
            "models_used": list(run_payload.get("models_used") or []),
        },
    }


def _build_trust_snapshot(
    *,
    trust_map: dict[str, dict[str, Any]],
    benchmark_snapshot: dict[str, Any],
    realism_scorecard: dict[str, Any],
) -> dict[str, Any]:
    confidence_counts = Counter(
        str(trust.get("confidence_label") or "Needs validation")
        for trust in trust_map.values()
    )
    agreement_counts = Counter(
        str(trust.get("agreement_label") or "Partial agreement")
        for trust in trust_map.values()
    )

    return {
        "confidence_summary": {
            "dominant_label": confidence_counts.most_common(1)[0][0] if confidence_counts else "Needs validation",
            "counts": dict(confidence_counts),
        },
        "agreement_summary": {
            "dominant_label": agreement_counts.most_common(1)[0][0] if agreement_counts else "Partial agreement",
            "counts": dict(agreement_counts),
        },
        "realism_snapshot": {
            "available": realism_scorecard.get("available", False),
            "label": _build_realism_label(realism_scorecard),
            "detail": _build_realism_detail(realism_scorecard),
        },
        "benchmark_snapshot": {
            "available": benchmark_snapshot.get("available", False),
            "label": (
                benchmark_snapshot.get("stability_summary")
                if benchmark_snapshot.get("available")
                else "Unavailable"
            ),
            "detail": (
                f"Top use case consensus: {benchmark_snapshot.get('top_use_case_consensus') or 'n/a'}."
                if benchmark_snapshot.get("available")
                else benchmark_snapshot.get("message")
            ),
        },
    }


def _build_top_findings(
    *,
    use_case_share: dict[str, Any],
    barrier_ranking: dict[str, Any],
    message_performance: dict[str, Any],
    interest_ladder: dict[str, Any],
    model_difference_chart: dict[str, Any],
    trust_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    if use_case_share.get("available") and use_case_share.get("rows"):
        top_row = use_case_share["rows"][0]
        trust = _aggregate_trust_labels(trust_map, ["Q3"])
        findings.append(
            {
                "id": "use-case",
                "title": "Top intended use",
                "headline": f"{top_row.get('label', 'Leading use case')} is the clearest use case signal.",
                "summary": (
                    f"It leads with {top_row.get('share', 0)}% share under the current synthetic run."
                ),
                "confidence_label": trust["confidence_label"],
                "agreement_label": trust["agreement_label"],
                "chart_kind": "horizontal_bar",
                "chart_rows": list(use_case_share.get("rows") or [])[:6],
            }
        )

    if barrier_ranking.get("available") and barrier_ranking.get("rows"):
        top_row = barrier_ranking["rows"][0]
        trust = _aggregate_trust_labels(
            trust_map,
            [str(row.get("question_id")) for row in barrier_ranking.get("rows") or []],
        )
        findings.append(
            {
                "id": "barriers",
                "title": "Barrier severity",
                "headline": f"{top_row.get('label', 'Top barrier')} is the heaviest objection signal.",
                "summary": (
                    f"It has the highest average severity score at {top_row.get('value', 'n/a')}."
                ),
                "confidence_label": trust["confidence_label"],
                "agreement_label": trust["agreement_label"],
                "chart_kind": "horizontal_rank",
                "chart_rows": list(barrier_ranking.get("rows") or [])[:7],
            }
        )

    if message_performance.get("available") and message_performance.get("rows"):
        top_row = max(
            message_performance["rows"],
            key=lambda row: float(row.get("purchase_avg") or 0.0),
        )
        concept_id = str(top_row.get("concept_id") or "")
        trust = _aggregate_trust_labels(
            trust_map,
            [f"{concept_id}A", f"{concept_id}B"] if concept_id else [],
        )
        findings.append(
            {
                "id": "message-performance",
                "title": "Positioning performance",
                "headline": f"{top_row.get('label', 'Leading concept')} looks strongest on purchase lift.",
                "summary": (
                    f"Appeal averages {top_row.get('appeal_avg', 'n/a')} and purchase averages "
                    f"{top_row.get('purchase_avg', 'n/a')}."
                ),
                "confidence_label": trust["confidence_label"],
                "agreement_label": trust["agreement_label"],
                "chart_kind": "grouped_bar",
                "chart_rows": list(message_performance.get("rows") or [])[:5],
            }
        )

    if interest_ladder.get("available") and interest_ladder.get("rows"):
        rows = list(interest_ladder.get("rows") or [])
        if len(rows) >= 2:
            largest_drop = max(
                (
                    {
                        "from": rows[index],
                        "to": rows[index + 1],
                        "delta": float(rows[index]["value"]) - float(rows[index + 1]["value"]),
                    }
                    for index in range(len(rows) - 1)
                ),
                key=lambda item: item["delta"],
            )
            headline = (
                f"The biggest drop is from {largest_drop['from']['label']} to {largest_drop['to']['label']}."
            )
        else:
            headline = "The interest ladder shows where momentum holds or fades."
        trust = _aggregate_trust_labels(trust_map, ["S3", "Q0B", "Q1", "Q2"])
        findings.append(
            {
                "id": "interest-ladder",
                "title": "Decision ladder",
                "headline": headline,
                "summary": "This progression shows where the audience moves from feasibility into purchase intent.",
                "confidence_label": trust["confidence_label"],
                "agreement_label": trust["agreement_label"],
                "chart_kind": "ladder",
                "chart_rows": rows,
            }
        )

    if model_difference_chart.get("available") and len(findings) < 5:
        findings.append(
            {
                "id": "model-differences",
                "title": "Model comparison",
                "headline": "Multiple models are not perfectly aligned on every directional signal.",
                "summary": "Review the spread before treating any single signal as final.",
                "confidence_label": "Needs validation",
                "agreement_label": "Partial agreement",
                "chart_kind": "difference",
                "chart_rows": list(model_difference_chart.get("rows") or [])[:5],
            }
        )

    return findings[:4]


def _build_segment_story(
    *,
    df: pd.DataFrame,
    segment_notes: list[str],
    segment_heatmap: dict[str, Any],
) -> dict[str, Any]:
    strongest_segment = _compute_strongest_segment(df)
    weakest_segment = _compute_weakest_segment(df)
    return {
        "strongest_segment": strongest_segment,
        "weakest_segment": weakest_segment,
        "notes": segment_notes[:5],
        "heatmap_available": segment_heatmap.get("available", False),
    }


def _build_barrier_ranking(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty or "question_id" not in df.columns:
        return {"available": False, "message": "No records available.", "rows": []}

    barrier_df = df[df["question_id"].astype(str).str.startswith("Q5_")].copy()
    if barrier_df.empty:
        return {"available": False, "message": "Barrier matrix items were not found in this run.", "rows": []}

    rows: list[dict[str, Any]] = []
    for question_id, qdf in barrier_df.groupby("question_id"):
        numeric = pd.to_numeric(qdf["answer"], errors="coerce").dropna()
        if numeric.empty:
            continue
        rows.append(
            {
                "question_id": str(question_id),
                "label": _compact_question_label(_safe_first_value(qdf, "question_text"), fallback=str(question_id)),
                "value": round(float(numeric.mean()), 2),
            }
        )

    rows.sort(key=lambda row: float(row["value"]), reverse=True)
    if not rows:
        return {"available": False, "message": "Barrier items were present but not numeric.", "rows": []}
    return {"available": True, "rows": rows}


def _build_message_performance(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"available": False, "message": "No records available.", "rows": []}

    rows: list[dict[str, Any]] = []
    for concept_number in range(9, 14):
        appeal_id = f"Q{concept_number}A"
        purchase_id = f"Q{concept_number}B"
        appeal_avg = _question_numeric_mean(df, appeal_id)
        purchase_avg = _question_numeric_mean(df, purchase_id)
        if appeal_avg is None and purchase_avg is None:
            continue
        rows.append(
            {
                "concept_id": f"Q{concept_number}",
                "label": f"Concept {concept_number}",
                "appeal_avg": round(appeal_avg, 2) if appeal_avg is not None else None,
                "purchase_avg": round(purchase_avg, 2) if purchase_avg is not None else None,
            }
        )

    if not rows:
        return {
            "available": False,
            "message": "Positioning concept pairs were not found in this run.",
            "rows": [],
        }
    return {"available": True, "rows": rows}


def _build_use_case_share(df: pd.DataFrame) -> dict[str, Any]:
    distribution = _compute_question_answer_distribution(df, "Q3")
    if getattr(distribution, "empty", True):
        return {"available": False, "message": "Primary use question Q3 was not found.", "rows": []}

    rows = [
        {
            "label": str(row.get("answer_display")),
            "count": int(row.get("count") or 0),
            "share": float(row.get("percentage") or 0.0),
        }
        for row in _dataframe_to_records(distribution)
    ]
    return {"available": True, "rows": rows}


def _build_interest_ladder(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"available": False, "message": "No records available.", "rows": []}

    rows: list[dict[str, Any]] = []
    for question_id, label in [
        ("S3", "Feasibility"),
        ("Q0B", "Category interest"),
        ("Q1", "Price-point interest"),
        ("Q2", "Purchase likelihood"),
    ]:
        qdf = df[df["question_id"].astype(str) == question_id].copy() if "question_id" in df.columns else pd.DataFrame()
        if qdf.empty:
            continue
        positive_share = _question_positive_share(qdf)
        if positive_share is None:
            continue
        rows.append(
            {
                "question_id": question_id,
                "label": label,
                "value": round(positive_share, 1),
                "measure": "positive_share",
            }
        )

    if not rows:
        return {"available": False, "message": "Core decision-ladder questions were not found.", "rows": []}
    return {"available": True, "rows": rows}


def _build_segment_heatmap(
    df: pd.DataFrame,
    barrier_ranking: dict[str, Any],
    message_performance: dict[str, Any],
) -> dict[str, Any]:
    segments = _list_segments(df)
    if not segments:
        return {"available": False, "message": "No segment labels were found in this run.", "segments": [], "rows": []}

    candidate_ids = ["Q1", "Q2", "Q3"]
    candidate_ids.extend(str(row.get("question_id")) for row in list(barrier_ranking.get("rows") or [])[:3])
    for row in list(message_performance.get("rows") or [])[:2]:
        concept_id = str(row.get("concept_id") or "")
        if concept_id:
            candidate_ids.extend([f"{concept_id}A", f"{concept_id}B"])

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for question_id in candidate_ids:
        if not question_id or question_id in seen:
            continue
        seen.add(question_id)
        qdf = df[df["question_id"].astype(str) == question_id].copy() if "question_id" in df.columns else pd.DataFrame()
        if qdf.empty:
            continue
        values: list[dict[str, Any]] = []
        has_numeric_value = False
        for segment in segments:
            sdf = qdf[qdf["segment_label"].astype(str) == segment].copy() if "segment_label" in qdf.columns else pd.DataFrame()
            mean_value = _numeric_mean_from_frame(sdf)
            if mean_value is not None:
                has_numeric_value = True
            values.append({"segment": segment, "value": round(mean_value, 2) if mean_value is not None else None})
        if not has_numeric_value:
            continue
        rows.append(
            {
                "question_id": question_id,
                "label": _compact_question_label(_safe_first_value(qdf, "question_text"), fallback=question_id),
                "values": values,
            }
        )

    if not rows:
        return {
            "available": False,
            "message": "Not enough numeric question-by-segment data was available for a heatmap.",
            "segments": segments,
            "rows": [],
        }
    return {"available": True, "segments": segments, "rows": rows[:8]}


def _build_model_difference_chart(df: pd.DataFrame) -> dict[str, Any]:
    models = _list_models(df)
    if len(models) < 2:
        return {
            "available": False,
            "message": "Not enough multi-model coverage to compare model differences.",
            "models": models,
            "rows": [],
        }

    rows: list[dict[str, Any]] = []
    if "question_id" not in df.columns:
        return {"available": False, "message": "Question ids unavailable.", "models": models, "rows": []}

    for question_id, qdf in df.groupby("question_id"):
        grouped = (
            qdf.assign(answer_num=pd.to_numeric(qdf["answer"], errors="coerce"))
            .groupby("model", dropna=True)["answer_num"]
            .mean()
            .dropna()
        )
        if len(grouped) < 2:
            continue
        spread = float(grouped.max() - grouped.min())
        rows.append(
            {
                "question_id": str(question_id),
                "label": _compact_question_label(_safe_first_value(qdf, "question_text"), fallback=str(question_id)),
                "spread": round(spread, 2),
                "values": [
                    {"model": str(model_name), "value": round(float(value), 2)}
                    for model_name, value in grouped.items()
                ],
            }
        )

    rows.sort(key=lambda row: float(row["spread"]), reverse=True)
    if not rows:
        return {
            "available": False,
            "message": "Current model outputs are not numeric enough for a compact comparison chart.",
            "models": models,
            "rows": [],
        }
    return {"available": True, "models": models, "rows": rows[:6]}


def _aggregate_trust_labels(
    trust_map: dict[str, dict[str, Any]],
    question_ids: list[str],
) -> dict[str, str]:
    relevant = [trust_map[question_id] for question_id in question_ids if question_id in trust_map]
    if not relevant:
        return {
            "confidence_label": "Needs validation",
            "agreement_label": "Partial agreement",
        }

    confidence = Counter(str(item.get("confidence_label") or "Needs validation") for item in relevant)
    agreement = Counter(str(item.get("agreement_label") or "Partial agreement") for item in relevant)
    return {
        "confidence_label": confidence.most_common(1)[0][0],
        "agreement_label": agreement.most_common(1)[0][0],
    }


def _first_question_numeric_mean(df: pd.DataFrame, question_ids: list[str]) -> Optional[float]:
    for question_id in question_ids:
        mean_value = _question_numeric_mean(df, question_id)
        if mean_value is not None:
            return mean_value
    return None


def _question_numeric_mean(df: pd.DataFrame, question_id: str) -> Optional[float]:
    if df.empty or "question_id" not in df.columns:
        return None
    qdf = df[df["question_id"].astype(str) == question_id].copy()
    return _numeric_mean_from_frame(qdf)


def _numeric_mean_from_frame(df: pd.DataFrame) -> Optional[float]:
    if df.empty or "answer" not in df.columns:
        return None
    numeric = pd.to_numeric(df["answer"], errors="coerce").dropna()
    if numeric.empty:
        return None
    return float(numeric.mean())


def _question_positive_share(qdf: pd.DataFrame) -> Optional[float]:
    if qdf.empty or "answer" not in qdf.columns:
        return None

    question_type = _safe_first_value(qdf, "question_type")
    answers = qdf["answer"]

    if question_type in {"likert", "numeric"}:
        numeric = pd.to_numeric(answers, errors="coerce").dropna()
        if numeric.empty:
            return None
        return float((numeric >= 4).mean() * 100)

    normalized = answers.dropna().astype(str).str.strip().str.lower()
    if normalized.empty:
        return None

    positive_tokens = ("yes", "definitely", "very", "likely", "extremely", "probably")
    negative_tokens = ("no", "unlikely", "not at all", "never")
    positives = normalized.apply(
        lambda value: any(token in value for token in positive_tokens)
        and not any(token in value for token in negative_tokens)
    )
    return float(positives.mean() * 100)


def _compute_strongest_segment(df: pd.DataFrame) -> str:
    segment_scores = _segment_score_table(df)
    if not segment_scores:
        segments = _list_segments(df)
        return segments[0] if segments else "N/A"
    return max(segment_scores.items(), key=lambda item: item[1])[0]


def _compute_weakest_segment(df: pd.DataFrame) -> str:
    segment_scores = _segment_score_table(df)
    if not segment_scores:
        return "N/A"
    return min(segment_scores.items(), key=lambda item: item[1])[0]


def _segment_score_table(df: pd.DataFrame) -> dict[str, float]:
    segments = _list_segments(df)
    if not segments:
        return {}

    scores: dict[str, float] = {}
    for segment in segments:
        segment_df = df[df["segment_label"].astype(str) == segment].copy() if "segment_label" in df.columns else pd.DataFrame()
        values = [
            value
            for value in (
                _question_numeric_mean(segment_df, "Q0B"),
                _question_numeric_mean(segment_df, "Q1"),
                _question_numeric_mean(segment_df, "Q2"),
            )
            if value is not None
        ]
        if values:
            scores[segment] = sum(values) / len(values)
    return scores


def _compact_question_label(text: Optional[str], *, fallback: str) -> str:
    if not text:
        return fallback
    normalized = " ".join(str(text).split())
    if len(normalized) <= 54:
        return normalized
    return f"{normalized[:51].rstrip()}..."


def _build_realism_label(realism_scorecard: dict[str, Any]) -> str:
    if not realism_scorecard.get("available"):
        return "Unavailable"
    summary = realism_scorecard.get("summary") or {}
    score = summary.get("realism_score")
    if score is None:
        return "Available"
    return f"{score} realism score"


def _build_realism_detail(realism_scorecard: dict[str, Any]) -> Optional[str]:
    if not realism_scorecard.get("available"):
        return realism_scorecard.get("message")
    summary = realism_scorecard.get("summary") or {}
    gap = summary.get("distribution_gap")
    questions = summary.get("questions_scored")
    if gap is None and questions is None:
        return "Detailed realism scoring is available."
    parts = []
    if gap is not None:
        parts.append(f"Distribution gap: {gap}")
    if questions is not None:
        parts.append(f"Questions scored: {questions}")
    return " • ".join(parts)


def product_url_autofill(*, settings: AppSettings, url: str) -> dict:
    if not settings.openrouter_api_key:
        raise ProviderUnavailableApiError("OPENROUTER_API_KEY is required for product URL autofill.")

    scraper = load_module("backend.scraper", settings.legacy_app_root)
    vision = load_module("backend.vision", settings.legacy_app_root)
    schemas = load_module("backend.schemas", settings.legacy_app_root)

    try:
        page_text = scraper.scrape_product_page(url)
        with temporary_env(
            {
                "OPENROUTER_API_KEY": settings.openrouter_api_key,
                "OPENROUTER_BASE_URL": settings.openrouter_base_url,
            }
        ):
            result = vision.generate_full_context_from_url(page_text)
        validated = schemas.BusinessProductContext(**result)
        return {
            "page_text": page_text,
            "product_patch": validated.model_dump(),
        }
    except ValidationError as exc:
        raise LegacyModuleApiError("Legacy URL autofill returned invalid product context.", {"errors": exc.errors()}) from exc
    except RuntimeError as exc:
        raise ProviderUnavailableApiError(str(exc)) from exc
    except Exception as exc:
        raise LegacyModuleApiError(f"Product URL autofill failed: {exc}") from exc


def product_image_analysis(*, settings: AppSettings, file_bytes: bytes) -> dict:
    service_account = load_service_account_info(
        settings.google_cloud_service_account_json,
        settings.google_cloud_service_account_path,
    )
    if not settings.google_cloud_api_key and service_account is None:
        raise ProviderUnavailableApiError("Google Vision credentials are required for product image analysis.")

    vision = load_module("backend.vision", settings.legacy_app_root)
    try:
        with temporary_env({"GOOGLE_CLOUD_API_KEY": settings.google_cloud_api_key}):
            analysis = vision.extract_full_analysis(file_bytes, service_account_info=service_account)
    except RuntimeError as exc:
        raise ProviderUnavailableApiError(str(exc)) from exc
    except Exception as exc:
        raise LegacyModuleApiError(f"Product image analysis failed: {exc}") from exc

    colors = []
    for color in analysis.get("colors", []):
        hex_value = str(color.get("hex", "")).strip()
        percentage = color.get("percentage")
        if not hex_value:
            continue
        if isinstance(percentage, (int, float)):
            colors.append(f"{hex_value} ({percentage:.1f}%)")
        else:
            colors.append(hex_value)

    return {
        "analysis": analysis,
        "product_patch": {
            "product_image_labels": analysis.get("labels", []),
            "product_image_objects": analysis.get("objects", []),
            "product_image_colors": colors,
        },
    }
