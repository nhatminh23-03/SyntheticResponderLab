from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import pandas as pd
from pydantic import ValidationError

from src.adapters.legacy_backend.runtime import load_module, load_service_account_info, temporary_env
from src.adapters.legacy_backend.survey_docx_fallback import parse_aytm_style_docx_to_validated_schema
from src.config.settings import AppSettings
from src.services.exceptions import LegacyModuleApiError, ProviderUnavailableApiError, ValidationApiError


_ANALYSIS_STOP_WORDS = {
    "about",
    "again",
    "also",
    "always",
    "among",
    "and",
    "any",
    "are",
    "because",
    "been",
    "being",
    "both",
    "but",
    "can",
    "could",
    "does",
    "doing",
    "each",
    "else",
    "for",
    "from",
    "had",
    "has",
    "have",
    "having",
    "her",
    "here",
    "him",
    "his",
    "how",
    "into",
    "its",
    "just",
    "like",
    "make",
    "more",
    "most",
    "much",
    "not",
    "now",
    "our",
    "out",
    "really",
    "same",
    "she",
    "should",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "too",
    "use",
    "very",
    "want",
    "was",
    "were",
    "what",
    "when",
    "with",
    "would",
    "you",
    "your",
}

_LIKERT_ORDER = {
    "1": 1,
    "strongly disagree": 1,
    "disagree": 2,
    "somewhat disagree": 3,
    "neutral": 4,
    "neither agree nor disagree": 4,
    "somewhat agree": 5,
    "agree": 6,
    "strongly agree": 7,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
}


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


def _generate_response_records_compat(run_manager: Any, **kwargs: Any) -> List[Any]:
    """Call legacy run_manager.generate_response_records across signature variants.

    The legacy app in this repository can drift independently from the API adapter.
    Some versions accept optional kwargs like allow_mock_fallback or
    user_instruction_template_override, while older versions do not.
    """

    generate_records = run_manager.generate_response_records

    return _call_with_supported_kwargs(generate_records, **kwargs)


def _call_with_supported_kwargs(function: Any, **kwargs: Any) -> Any:
    """Call a function while safely dropping unsupported keyword arguments."""

    try:
        signature = inspect.signature(function)
        accepts_var_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )

        if accepts_var_kwargs:
            return function(**kwargs)

        filtered_kwargs = {
            key: value for key, value in kwargs.items() if key in signature.parameters
        }
        return function(**filtered_kwargs)
    except (TypeError, ValueError):
        return function(**kwargs)


def _run_simulation_compat(run_manager: Any, **kwargs: Any) -> Any:
    """Call whichever simulation entrypoint exists in the loaded legacy run manager."""

    run_simulation = getattr(run_manager, "run_simulation", None)
    if callable(run_simulation):
        return _call_with_supported_kwargs(run_simulation, **kwargs)

    run_mock_simulation = getattr(run_manager, "run_mock_simulation", None)
    if callable(run_mock_simulation):
        return _call_with_supported_kwargs(run_mock_simulation, **kwargs)

    raise AttributeError(
        "Legacy run_manager exposes neither run_simulation nor run_mock_simulation."
    )


def _build_prompt_override_sections(
    *,
    persona: Any,
    survey_schema: Any,
    business_product_context: Any,
    market_context: Any,
    audience_filter: Any,
) -> Dict[str, str]:
    survey_lines = [f"- Title: {survey_schema.survey_title}"]
    for index, question in enumerate(survey_schema.questions, start=1):
        survey_lines.append(
            f"{index}. {question.id} [{question.question_type}] {question.text}"
        )
        options = list(getattr(question, "options", []) or [])
        if options:
            survey_lines.append(f"   Options: {', '.join(str(option) for option in options)}")

    persona_lines = [
        f"- Persona ID: {getattr(persona, 'persona_id', '')}",
        f"- Segment: {getattr(persona, 'segment_label', '') or 'General Segment'}",
        f"- Fit tier: {getattr(persona, 'fit_tier', '') or 'unspecified'}",
    ]
    likely_use_case = getattr(persona, "likely_use_case", None)
    if likely_use_case:
        persona_lines.append(f"- Likely use case: {likely_use_case}")
    likely_barrier = getattr(persona, "likely_barrier", None)
    if likely_barrier:
        persona_lines.append(f"- Likely barrier: {likely_barrier}")

    audience_lines: List[str] = []
    if audience_filter is not None:
        audience_dump = audience_filter.model_dump(exclude_none=True)
        for key, value in audience_dump.items():
            audience_lines.append(f"- {key}: {value}")

    product_lines: List[str] = []
    if business_product_context is not None:
        product_dump = business_product_context.model_dump(exclude_none=True)
        for key, value in product_dump.items():
            if isinstance(value, list):
                if value:
                    product_lines.append(f"- {key}: {', '.join(str(item) for item in value)}")
            elif value not in (None, "", []):
                product_lines.append(f"- {key}: {value}")

    market_lines: List[str] = []
    if market_context is not None:
        market_dump = market_context.model_dump(exclude_none=True)
        for key, value in market_dump.items():
            if key == "direct_competitors" and value:
                market_lines.append("- Direct competitors:")
                for competitor in value:
                    name = competitor.get("name") or "Unnamed competitor"
                    product_type = competitor.get("product_type") or "Unknown type"
                    market_lines.append(f"  - {name} ({product_type})")
                continue
            if isinstance(value, list):
                if value:
                    market_lines.append(f"- {key}: {', '.join(str(item) for item in value)}")
            elif value not in (None, "", []):
                market_lines.append(f"- {key}: {value}")

    output_contract = json.dumps(
        {
            "answers": [
                {
                    "question_id": "<question id>",
                    "answer": "<answer value matching question type>",
                }
            ]
        },
        ensure_ascii=False,
    )

    return {
        "persona_section": "Persona\n" + "\n".join(persona_lines),
        "survey_section": "Survey\n" + "\n".join(survey_lines),
        "audience_section": "Audience\n" + ("\n".join(audience_lines) if audience_lines else "- None provided"),
        "product_section": "Product\n" + ("\n".join(product_lines) if product_lines else "- None provided"),
        "market_section": "Market\n" + ("\n".join(market_lines) if market_lines else "- None provided"),
        "return_format": (
            "Return strict JSON only.\n"
            "Output requirements:\n"
            "1) Return one answer per question id.\n"
            "2) For single_choice, answer must be one listed option exactly.\n"
            "3) For multi_choice, answer must be a JSON array of listed options.\n"
            "4) For likert/numeric, answer must be numeric and within min/max when provided.\n"
            "5) For open_text, answer must be a concise string.\n"
            f"6) Match this contract:\n{output_contract}"
        ),
    }


def _build_prompt_payload_with_override(
    *,
    prompt_builder: Any,
    prompt_user_template_override: Optional[str],
    persona: Any,
    survey_schema: Any,
    business_product_context: Any,
    market_context: Any,
    audience_filter: Any,
) -> Dict[str, Any]:
    payload = prompt_builder.build_openrouter_prompt_payload(
        persona=persona,
        survey_schema=survey_schema,
        business_product_context=business_product_context,
        market_context=market_context,
        audience_filter=audience_filter,
    )
    if not prompt_user_template_override:
        return payload

    sections = _build_prompt_override_sections(
        persona=persona,
        survey_schema=survey_schema,
        business_product_context=business_product_context,
        market_context=market_context,
        audience_filter=audience_filter,
    )
    user_instruction = prompt_user_template_override
    for key, value in sections.items():
        user_instruction = user_instruction.replace(f"{{{{{key}}}}}", value)

    messages = list(payload.get("messages", []))
    if len(messages) >= 2 and isinstance(messages[1], dict):
        messages[1] = {**messages[1], "content": user_instruction}
    else:
        messages = [
            {"role": "system", "content": "Return strict JSON only with no prose or markdown."},
            {"role": "user", "content": user_instruction},
        ]
    return {
        **payload,
        "messages": messages,
    }


def _extract_provider_error_detail(result: Dict[str, Any]) -> str:
    raw_text = str(result.get("raw_text") or "").strip()
    if raw_text:
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                error_value = parsed.get("error")
                if isinstance(error_value, dict):
                    message = str(error_value.get("message") or "").strip()
                    if message:
                        return message
                message = str(parsed.get("message") or "").strip()
                if message:
                    return message
        except Exception:
            pass
        return raw_text[:500]
    return str(result.get("error") or "Unknown provider error").strip()


def _generate_live_response_records_with_debug(
    *,
    schemas: Any,
    run_manager: Any,
    llm_client: Any,
    prompt_builder: Any,
    config: Any,
    survey_schema: Any,
    audience_filter: Any,
    persona_profiles: List[Any],
    business_product_context: Any,
    market_context: Any,
    prompt_user_template_override: Optional[str],
    openrouter_timeout_sec: int = 45,
) -> tuple[List[Any], Dict[str, Any]]:
    extract_answer_map = getattr(run_manager, "_extract_answer_map_from_openrouter_result")
    coerce_answer = getattr(run_manager, "_coerce_openrouter_answer_value")
    generate_mock_answer = getattr(run_manager, "_generate_mock_answer")
    build_context_signals = getattr(run_manager, "_build_context_signals")
    build_market_signals = getattr(run_manager, "_build_market_signals")

    context_signals = build_context_signals(business_product_context)
    market_signals = build_market_signals(market_context, business_product_context)

    respondent_model_pairs: List[tuple[str, str, int, Optional[int]]] = []
    if config.experiment_mode == "mirror":
        for respondent_index in range(1, config.sample_size + 1):
            for model in config.selected_models:
                respondent_model_pairs.append((f"RESP_{respondent_index:03d}", model, respondent_index, None))
    elif config.experiment_mode == "stability":
        model = config.selected_models[0]
        for respondent_index in range(1, config.sample_size + 1):
            for rerun in range(1, config.reruns_per_persona + 1):
                respondent_model_pairs.append((f"RESP_{respondent_index:03d}_R{rerun}", model, respondent_index, rerun))
    else:
        for respondent_index in range(1, config.sample_size + 1):
            model = config.selected_models[(respondent_index - 1) % len(config.selected_models)]
            respondent_model_pairs.append((f"RESP_{respondent_index:03d}", model, respondent_index, None))

    request_errors = 0
    provider_error_count = 0
    malformed_json_count = 0
    fallback_count = 0
    parsed_count = 0
    records: List[Any] = []

    for respondent_id, model_name, respondent_index, rerun in respondent_model_pairs:
        persona = persona_profiles[(respondent_index - 1) % len(persona_profiles)]
        segment_label = persona.segment_label or "General Segment"
        prompt_payload = _build_prompt_payload_with_override(
            prompt_builder=prompt_builder,
            prompt_user_template_override=prompt_user_template_override,
            persona=persona,
            survey_schema=survey_schema,
            business_product_context=business_product_context,
            market_context=market_context,
            audience_filter=audience_filter,
        )
        result = llm_client.generate_survey_response_with_openrouter(
            model_name=model_name,
            prompt_payload=prompt_payload,
            timeout=openrouter_timeout_sec,
        )
        if not bool(result.get("ok")):
            request_errors += 1
            status_code = result.get("status_code")
            error_text = str(result.get("error") or "").lower()
            if status_code in {401, 403}:
                detail = _extract_provider_error_detail(result)
                raise LegacyModuleApiError(f"OpenRouter authentication failed: {detail}")
            if status_code and int(status_code) >= 400:
                provider_error_count += 1
            if "json" in error_text:
                malformed_json_count += 1

        parsed_answers = extract_answer_map(result)
        for question_index, question in enumerate(survey_schema.questions, start=1):
            answer_value = parsed_answers.get(question.id)
            validated_answer = coerce_answer(question, answer_value)
            if validated_answer is None:
                fallback_count += 1
                validated_answer = generate_mock_answer(
                    question=question,
                    persona=persona,
                    model=model_name,
                    context_signals=context_signals,
                    market_signals=market_signals,
                    respondent_index=respondent_index,
                    question_index=question_index,
                    rerun=rerun,
                )
            else:
                parsed_count += 1

            records.append(
                schemas.MockResponseRecord(
                    respondent_id=respondent_id,
                    model=model_name,
                    experiment_mode=config.experiment_mode,
                    survey_title=config.survey_title,
                    question_id=question.id,
                    question_text=question.text,
                    question_type=question.question_type,
                    answer=validated_answer,
                    segment_label=segment_label,
                    run_id=config.run_id,
                )
            )

    generation_debug = {
        "generation_mode": "openrouter_live",
        "model": config.selected_models[0] if len(config.selected_models) == 1 else None,
        "respondents": int(len(respondent_model_pairs)),
        "questions_total": int(len(records)),
        "request_errors": int(request_errors),
        "provider_error_count": int(provider_error_count),
        "malformed_json_count": int(malformed_json_count),
        "questions_fallback_to_mock": int(fallback_count),
        "questions_parsed_from_live": int(parsed_count),
    }
    return records, generation_debug


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
    prompt_user_template_override: Optional[str] = None,
) -> dict:
    schemas = load_module("backend.schemas", settings.legacy_app_root)
    run_manager = load_module("backend.simulation.run_manager", settings.legacy_app_root)
    persona_generator = load_module("backend.simulation.persona_generator", settings.legacy_app_root)
    prior_sampler = load_module("backend.grounding.prior_sampler", settings.legacy_app_root)
    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)
    prompt_builder = load_module("backend.simulation.prompt_builder", settings.legacy_app_root)

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

    if not openrouter_available:
        raise ProviderUnavailableApiError("OPENROUTER_API_KEY is required for live OpenRouter survey generation.")

    generation_mode = "openrouter_live"
    provider_model_name = experiment.selected_models[0] if len(experiment.selected_models) == 1 else None
    run_id = f"RUN_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    config = schemas.SimulationRunConfig(
        run_id=run_id,
        survey_title=survey_schema.survey_title,
        survey_question_count=len(survey_schema.questions),
        sample_size=experiment.sample_size,
        selected_models=experiment.selected_models or ["openai/gpt-4o-mini"],
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
            records, generation_debug = _generate_live_response_records_with_debug(
                schemas=schemas,
                run_manager=run_manager,
                llm_client=llm_client,
                prompt_builder=prompt_builder,
                config=config,
                survey_schema=survey_schema,
                audience_filter=audience,
                persona_profiles=personas,
                business_product_context=business_product_context,
                market_context=market_context,
                prompt_user_template_override=prompt_user_template_override,
            )
            result = _run_simulation_compat(
                run_manager,
                config=config,
                generation_mode=generation_mode,
                provider_model_name=provider_model_name,
                records=records,
            )
    except LegacyModuleApiError:
        raise
    except Exception as exc:
        raise LegacyModuleApiError(f"Simulation execution failed: {exc}") from exc

    warnings: List[str] = []
    fallback_count = int(generation_debug.get("questions_fallback_to_mock", 0) or 0)
    parsed_count = int(generation_debug.get("questions_parsed_from_live", 0) or 0)
    request_errors = int(generation_debug.get("request_errors", 0) or 0)
    provider_error_count = int(generation_debug.get("provider_error_count", 0) or 0)
    malformed_json_count = int(generation_debug.get("malformed_json_count", 0) or 0)
    if provider_error_count > 0:
        warnings.append(
            f"OpenRouter returned {provider_error_count} provider-level error(s); temporary deterministic fallback filled the missing answers."
        )
    if malformed_json_count > 0:
        warnings.append(
            f"OpenRouter returned malformed JSON for {malformed_json_count} respondent request(s); temporary fallback filled the missing answers."
        )
    if request_errors > 0 and provider_error_count == 0 and malformed_json_count == 0:
        warnings.append(
            "OpenRouter live generation hit provider or parsing errors; temporary deterministic fallback filled the missing answers."
        )
    if fallback_count > 0:
        warnings.append(
            f"Temporary migration fallback was used for {fallback_count} question(s); {parsed_count} question(s) were parsed from live model output."
        )
    if fallback_count > 0 and parsed_count == 0:
        warnings.append("This run completed with temporary deterministic fallback for every saved answer because no usable live answers were parsed.")
    if persona_generation_mode == "heuristic_fallback":
        warnings.append("Grounded priors unavailable; personas used heuristic fallback.")
    if geography_context and not geography_context.get("puma"):
        warnings.append("Geography context was partial; geo-aware priors may have fallen back to global tables.")
    if not geography_context and audience_payload.get("zip_code"):
        warnings.append("ZIP was provided, but geography context could not be resolved; geo-aware priors stayed global.")
    run_debug_summary = _build_run_debug_summary(
        generation_debug=generation_debug,
        personas=personas,
        prior_notes=prior_notes,
    )

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
        "provider_model_name": provider_model_name,
        "persona_generation_mode": persona_generation_mode,
        "grounded_priors_available": grounded_priors_available,
        "cex_affordability_available": affordability_priors_available,
        "geography_context": geography_context,
        "prior_notes": prior_notes,
        "warnings": warnings,
        "generation_debug": generation_debug,
        "run_debug_summary": run_debug_summary,
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
    llm_client = load_module("backend.simulation.llm_client", settings.legacy_app_root)
    prompt_builder = load_module("backend.simulation.prompt_builder", settings.legacy_app_root)

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

    if not openrouter_available:
        raise ProviderUnavailableApiError("OPENROUTER_API_KEY is required for live OpenRouter stability checks.")

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
            with temporary_env(
                {
                    "OPENROUTER_API_KEY": settings.openrouter_api_key,
                    "OPENROUTER_BASE_URL": settings.openrouter_base_url,
                }
            ):
                records, generation_debug = _generate_live_response_records_with_debug(
                    schemas=schemas,
                    run_manager=run_manager,
                    llm_client=llm_client,
                    prompt_builder=prompt_builder,
                    config=config,
                    survey_schema=survey_schema,
                    audience_filter=audience,
                    persona_profiles=personas,
                    business_product_context=business_product_context,
                    market_context=market_context,
                    prompt_user_template_override=None,
                )
            run_summaries.append(
                stability.summarize_run_outputs(records=records, personas=personas)
            )
            request_errors = int(generation_debug.get("request_errors", 0) or 0)
            fallback_count = int(generation_debug.get("questions_fallback_to_mock", 0) or 0)
            if request_errors > 0 or fallback_count > 0:
                warnings.append(
                    f"Stability rerun {rerun_index} used temporary deterministic fallback for {fallback_count} question(s) after {request_errors} live request error(s)."
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
    survey_payload: Optional[Dict[str, Any]],
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
    question_options = _build_question_options(df, survey_payload=survey_payload)

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
    dashboard_questions = _build_analysis_dashboard_questions(
        filtered_df=filtered_df,
        question_options=question_options,
        open_text_limit=open_text_limit,
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
        "dashboard": {
            "model_options": model_options,
            "selected_model": selected_model,
            "questions": dashboard_questions,
        },
        "run_debug_summary": latest_run_payload.get("run_debug_summary"),
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
    context_notes = {
        "model_notes": model_notes,
        "segment_notes": segment_notes,
        "run_warnings": list(latest_run_payload.get("warnings") or []),
        "survey_parse_warnings": list(latest_run_payload.get("survey_parse_warnings") or []),
    }
    evidence_package = _build_insights_evidence_package(
        latest_run_payload=latest_run_payload,
        executive_summary=executive_summary,
        trust_snapshot=trust_snapshot,
        top_findings=top_findings,
        charts={
            "barrier_ranking": barrier_ranking,
            "message_performance": message_performance,
            "use_case_share": use_case_share,
            "model_difference": model_difference_chart,
        },
        segment_story=segment_story,
        context_notes=context_notes,
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
        "context_notes": context_notes,
        "evidence_package": evidence_package,
    }


def _build_insights_evidence_package(
    *,
    latest_run_payload: Dict[str, Any],
    executive_summary: dict[str, Any],
    trust_snapshot: dict[str, Any],
    top_findings: list[dict[str, Any]],
    charts: dict[str, dict[str, Any]],
    segment_story: dict[str, Any],
    context_notes: dict[str, Any],
) -> dict[str, Any]:
    run_context = {
        "run_id": latest_run_payload.get("run_id"),
        "survey_title": latest_run_payload.get("survey_title"),
        "experiment_mode": latest_run_payload.get("experiment_mode"),
        "models_used": list(latest_run_payload.get("models_used") or []),
        "respondent_count": executive_summary.get("records_summary", {}).get("unique_respondents"),
        "question_count": executive_summary.get("records_summary", {}).get("questions"),
    }
    debug_summary = latest_run_payload.get("run_debug_summary") or {}
    items: list[dict[str, Any]] = []

    def add_item(
        evidence_id: str,
        category: str,
        title: str,
        summary: str,
        *,
        metrics: Optional[dict[str, Any]] = None,
    ) -> None:
        item: dict[str, Any] = {
            "id": evidence_id,
            "category": category,
            "title": title,
            "summary": summary,
        }
        if metrics:
            item["metrics"] = metrics
        items.append(item)

    top_use_case = executive_summary.get("top_use_case") or {}
    if top_use_case.get("label"):
        add_item(
            "exec_top_use_case",
            "executive_metric",
            "Top use case",
            f"{top_use_case.get('label')} is the strongest surfaced use case in this run.",
            metrics={"share": top_use_case.get("share")},
        )

    average_interest = executive_summary.get("average_interest")
    if average_interest is not None:
        add_item(
            "exec_average_interest",
            "executive_metric",
            "Average interest",
            "Average interest reflects the directional purchase-oriented score across the latest run.",
            metrics={"average_interest": average_interest},
        )

    strongest_segment = executive_summary.get("strongest_segment")
    if strongest_segment:
        add_item(
            "exec_strongest_segment",
            "executive_metric",
            "Strongest segment",
            f"{strongest_segment} currently shows the strongest overall interest-oriented pattern.",
        )

    model_difference = executive_summary.get("model_difference") or {}
    if model_difference.get("status"):
        add_item(
            "exec_model_difference",
            "executive_metric",
            "Model difference",
            str(model_difference.get("note") or "Model spread is summarized for the latest run."),
            metrics={
                "status": model_difference.get("status"),
                "differing_questions": model_difference.get("differing_questions"),
            },
        )

    for index, finding in enumerate(top_findings[:5], start=1):
        add_item(
            f"finding_{index}",
            "top_finding",
            str(finding.get("title") or f"Finding {index}"),
            f"{finding.get('headline') or ''} {finding.get('summary') or ''}".strip(),
            metrics={
                "confidence_label": finding.get("confidence_label"),
                "agreement_label": finding.get("agreement_label"),
            },
        )

    for index, row in enumerate((charts.get("barrier_ranking") or {}).get("rows") or [], start=1):
        if index > 3:
            break
        add_item(
            f"barrier_{index}",
            "barrier",
            str(row.get("label") or f"Barrier {index}"),
            f"{row.get('label') or 'Barrier'} is one of the strongest reported friction points in the latest run.",
            metrics={"value": row.get("value"), "question_id": row.get("question_id")},
        )

    for index, row in enumerate((charts.get("use_case_share") or {}).get("rows") or [], start=1):
        if index > 3:
            break
        add_item(
            f"use_case_{index}",
            "use_case",
            str(row.get("label") or f"Use case {index}"),
            f"{row.get('label') or 'Use case'} represents a meaningful share of intended usage.",
            metrics={"count": row.get("count"), "share": row.get("share")},
        )

    for index, row in enumerate((charts.get("message_performance") or {}).get("rows") or [], start=1):
        if index > 3:
            break
        add_item(
            f"concept_{index}",
            "message_performance",
            str(row.get("label") or f"Concept {index}"),
            f"{row.get('label') or 'Concept'} is benchmarked on appeal and purchase-oriented response.",
            metrics={
                "appeal_avg": row.get("appeal_avg"),
                "purchase_avg": row.get("purchase_avg"),
            },
        )

    for index, note in enumerate((segment_story.get("notes") or [])[:3], start=1):
        add_item(
            f"segment_note_{index}",
            "segment_story",
            f"Segment note {index}",
            str(note),
        )

    confidence_summary = (trust_snapshot.get("confidence_summary") or {}).get("dominant_label")
    if confidence_summary:
        add_item(
            "trust_confidence",
            "trust",
            "Confidence summary",
            f"The dominant confidence label for the current findings is {confidence_summary}.",
            metrics={"counts": (trust_snapshot.get("confidence_summary") or {}).get("counts")},
        )

    agreement_summary = (trust_snapshot.get("agreement_summary") or {}).get("dominant_label")
    if agreement_summary:
        add_item(
            "trust_agreement",
            "trust",
            "Agreement summary",
            f"The dominant agreement label for the current findings is {agreement_summary}.",
            metrics={"counts": (trust_snapshot.get("agreement_summary") or {}).get("counts")},
        )

    realism_snapshot = trust_snapshot.get("realism_snapshot") or {}
    if realism_snapshot.get("label"):
        add_item(
            "realism_snapshot",
            "realism",
            "Realism snapshot",
            str(realism_snapshot.get("detail") or realism_snapshot.get("label")),
            metrics={"label": realism_snapshot.get("label")},
        )

    benchmark_snapshot = trust_snapshot.get("benchmark_snapshot") or {}
    if benchmark_snapshot.get("label"):
        add_item(
            "benchmark_snapshot",
            "benchmark",
            "Benchmark snapshot",
            str(benchmark_snapshot.get("detail") or benchmark_snapshot.get("label")),
            metrics={"label": benchmark_snapshot.get("label")},
        )

    if debug_summary:
        add_item(
            "run_debug_summary",
            "run_caveat",
            "Run debug summary",
            "Live-path execution diagnostics for the latest run.",
            metrics={
                "live_answer_rate": debug_summary.get("live_answer_rate"),
                "truly_live_answers": debug_summary.get("truly_live_answers"),
                "fallback_answers": debug_summary.get("fallback_answers"),
                "provider_error_count": debug_summary.get("provider_error_count"),
                "malformed_json_count": debug_summary.get("malformed_json_count"),
            },
        )

    for index, warning in enumerate((context_notes.get("run_warnings") or [])[:3], start=1):
        add_item(
            f"run_warning_{index}",
            "run_caveat",
            f"Run warning {index}",
            str(warning),
        )

    for index, warning in enumerate((context_notes.get("survey_parse_warnings") or [])[:2], start=1):
        add_item(
            f"survey_warning_{index}",
            "survey_caveat",
            f"Survey warning {index}",
            str(warning),
        )

    return {
        "version": "simulation_insights_evidence_v1",
        "from_run_id": latest_run_payload.get("run_id"),
        "run_context": run_context,
        "items": items,
    }


def _build_run_debug_summary(
    *,
    generation_debug: dict[str, Any],
    personas: list[Any],
    prior_notes: list[dict[str, Any]],
) -> dict[str, Any]:
    total_answers = int(generation_debug.get("questions_total", 0) or 0)
    live_answers = int(
        generation_debug.get("truly_live_answers", generation_debug.get("questions_parsed_from_live", 0)) or 0
    )
    fallback_answers = int(generation_debug.get("questions_fallback_to_mock", 0) or 0)
    provider_error_count = int(generation_debug.get("provider_error_count", 0) or 0)
    malformed_json_count = int(generation_debug.get("malformed_json_count", 0) or 0)

    return {
        "primary_live_path": generation_debug.get("generation_mode") == "openrouter_live",
        "total_answers": total_answers,
        "truly_live_answers": live_answers,
        "fallback_answers": fallback_answers,
        "provider_error_count": provider_error_count,
        "malformed_json_count": malformed_json_count,
        "live_answer_rate": round((live_answers / total_answers), 3) if total_answers > 0 else None,
        "ml_persona_completion_enabled": _ml_completion_enabled(personas=personas, prior_notes=prior_notes),
    }


def _ml_completion_enabled(*, personas: list[Any], prior_notes: list[dict[str, Any]]) -> bool:
    for persona in personas:
        if isinstance(persona, dict) and persona.get("ml_inference"):
            return True
        if getattr(persona, "ml_inference", None):
            return True

    for note in prior_notes:
        if str(note.get("prior_table_name") or "") != "ml_persona_completion":
            continue
        notes_text = str(note.get("notes") or "").lower()
        if "applied" in notes_text:
            return True
    return False


def _build_question_options(
    df: pd.DataFrame,
    *,
    survey_payload: Optional[Dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    seen_question_ids: set[str] = set()
    response_counts: dict[str, int] = {}
    response_meta_by_question_id: dict[str, dict[str, Any]] = {}

    if not df.empty and "question_id" in df.columns:
        response_counts = (
            df["question_id"]
            .astype(str)
            .value_counts()
            .to_dict()
        )
    if not df.empty and {"question_id", "question_text", "question_type"}.issubset(df.columns):
        response_meta = (
            df[["question_id", "question_text", "question_type"]]
            .drop_duplicates()
            .to_dict(orient="records")
        )
        response_meta_by_question_id = {
            str(row.get("question_id") or ""): row
            for row in response_meta
            if str(row.get("question_id") or "").strip()
        }

    survey_questions = list((survey_payload or {}).get("questions") or [])
    for index, question in enumerate(survey_questions):
        question_id = str(question.get("id") or "").strip()
        if not question_id:
            continue
        if response_counts and question_id not in response_counts:
            continue
        seen_question_ids.add(question_id)
        response_meta = response_meta_by_question_id.get(question_id) or {}
        options.append(
            {
                "id": question_id,
                "text": str(response_meta.get("question_text") or question.get("text") or question_id),
                "question_type": str(response_meta.get("question_type") or question.get("question_type") or ""),
                "response_count": int(response_counts.get(question_id, 0)),
                "question_order": index + 1,
                "option_values": _extract_question_option_values(question),
            }
        )

    if df.empty or not {"question_id", "question_text", "question_type"}.issubset(df.columns):
        return options

    question_meta = (
        df[["question_id", "question_text", "question_type"]]
        .drop_duplicates()
        .to_dict(orient="records")
    )
    question_meta.sort(
        key=lambda row: _question_sort_key(
            str(row.get("question_id") or ""),
            str(row.get("question_text") or ""),
        )
    )

    next_order = len(options) + 1
    for row in question_meta:
        question_id = str(row["question_id"])
        if question_id in seen_question_ids:
            continue
        options.append(
            {
                "id": question_id,
                "text": str(row["question_text"]),
                "question_type": str(row["question_type"]),
                "response_count": int(response_counts.get(question_id, 0)),
                "question_order": next_order,
                "option_values": [],
            }
        )
        next_order += 1
    return options


def _extract_question_option_values(question: dict[str, Any]) -> list[str]:
    raw_options = question.get("options")
    if isinstance(raw_options, list):
        option_values = [str(option).strip() for option in raw_options if str(option).strip()]
        if option_values:
            return option_values

    min_value = question.get("min_value")
    max_value = question.get("max_value")
    if isinstance(min_value, (int, float)) and isinstance(max_value, (int, float)):
        minimum = int(min_value)
        maximum = int(max_value)
        if minimum <= maximum and maximum - minimum <= 20:
            return [str(value) for value in range(minimum, maximum + 1)]

    return []


def _question_sort_key(question_id: str, question_text: str) -> tuple[str, int, str]:
    candidate = question_id or question_text
    match = re.search(r"(\d+)", candidate)
    prefix = re.sub(r"\d+", "", candidate).strip().lower()
    return (prefix, int(match.group(1)) if match else 10**9, candidate.lower())


def _build_analysis_dashboard_questions(
    *,
    filtered_df: pd.DataFrame,
    question_options: list[dict[str, Any]],
    open_text_limit: int,
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []

    for option in question_options:
        question_id = str(option.get("id") or "")
        question_df = (
            filtered_df[filtered_df["question_id"].astype(str) == question_id].copy()
            if not filtered_df.empty and "question_id" in filtered_df.columns
            else pd.DataFrame()
        )
        question_type = str(option.get("question_type") or _safe_first_value(question_df, "question_type") or "")
        chart_kind = _resolve_dashboard_chart_kind(question_df, question_type)
        question_payload: dict[str, Any] = {
            "question_id": question_id,
            "question_text": str(option.get("text") or _safe_first_value(question_df, "question_text") or question_id),
            "question_type": question_type,
            "question_order": int(option.get("question_order") or 0),
            "response_count": int(len(question_df)),
            "chart_kind": chart_kind,
        }

        if chart_kind in {"categorical_bar", "likert"}:
            distribution_df = _compute_question_answer_distribution(question_df, question_id)
            question_payload["distribution"] = _shape_distribution_rows(
                distribution_df,
                chart_kind=chart_kind,
                declared_options=list(option.get("option_values") or []),
            )
        elif chart_kind == "histogram":
            question_payload["histogram_bins"] = _compute_histogram_bins(question_df)
        elif chart_kind == "line":
            question_payload["line_points"] = _compute_time_series_points(question_df)
        elif chart_kind == "word_cloud":
            question_payload["word_cloud_terms"] = _build_word_cloud_terms(question_df)
            question_payload["quotes"] = _build_open_text_quotes(
                question_df,
                limit=min(max(open_text_limit, 3), 5),
            )

        questions.append(question_payload)

    return questions


def _resolve_dashboard_chart_kind(question_df: pd.DataFrame, question_type: str) -> str:
    normalized = str(question_type or "").strip().lower()

    if normalized == "open_text":
        return "word_cloud"
    if normalized == "likert":
        return "likert"
    if normalized in {"single_choice", "multi_choice"}:
        return "categorical_bar"
    if normalized in {"numeric", "number", "continuous", "slider"}:
        return "line" if _answers_are_time_like(question_df) else "histogram"

    if _answers_are_time_like(question_df):
        return "line"
    if _answers_are_numeric(question_df):
        return "histogram"
    return "categorical_bar"


def _shape_distribution_rows(
    distribution_df: pd.DataFrame,
    *,
    chart_kind: str,
    declared_options: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    if distribution_df.empty and not declared_options:
        return []

    rows = _dataframe_to_records(distribution_df)
    total = sum(int(row.get("count") or 0) for row in rows)

    if declared_options:
        counts_by_label = {
            str(row.get("answer_display") or "No answer"): int(row.get("count") or 0)
            for row in rows
        }
        ordered_rows = []
        seen_labels: set[str] = set()
        for option in declared_options:
            label = str(option or "").strip()
            if not label:
                continue
            seen_labels.add(label)
            count = counts_by_label.get(label, 0)
            ordered_rows.append(
                {
                    "label": label,
                    "count": count,
                    "percentage": round((count / total * 100), 1) if total else 0.0,
                }
            )

        extras = [
            {
                "label": str(row.get("answer_display") or "No answer"),
                "count": int(row.get("count") or 0),
                "percentage": float(row.get("percentage") or 0),
            }
            for row in rows
            if str(row.get("answer_display") or "No answer") not in seen_labels
        ]
        if chart_kind == "likert":
            extras.sort(key=lambda row: _likert_sort_key(str(row.get("label") or "")))
        else:
            extras.sort(
                key=lambda row: (
                    -int(row.get("count") or 0),
                    str(row.get("label") or "").lower(),
                )
            )
        return ordered_rows + extras

    if chart_kind == "likert":
        rows.sort(key=lambda row: _likert_sort_key(str(row.get("answer_display") or "")))
    else:
        rows.sort(
            key=lambda row: (
                -int(row.get("count") or 0),
                str(row.get("answer_display") or "").lower(),
            )
        )

    return [
        {
            "label": str(row.get("answer_display") or "No answer"),
            "count": int(row.get("count") or 0),
            "percentage": float(row.get("percentage") or 0),
        }
        for row in rows
    ]


def _likert_sort_key(label: str) -> tuple[int, str]:
    normalized = str(label or "").strip().lower()
    if normalized in _LIKERT_ORDER:
        return (_LIKERT_ORDER[normalized], normalized)

    try:
        return (int(float(normalized)), normalized)
    except ValueError:
        return (10**6, normalized)


def _answers_are_numeric(question_df: pd.DataFrame) -> bool:
    if question_df.empty or "answer" not in question_df.columns:
        return False
    numeric = pd.to_numeric(question_df["answer"], errors="coerce")
    return bool(numeric.notna().any())


def _answers_are_time_like(question_df: pd.DataFrame) -> bool:
    if question_df.empty or "answer" not in question_df.columns:
        return False

    answer_series = question_df["answer"].dropna().astype(str)
    if answer_series.empty:
        return False

    string_like_ratio = answer_series.str.contains(
        r"[-/]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec",
        case=False,
        regex=True,
    ).mean()
    parsed = pd.to_datetime(answer_series, errors="coerce")
    parsed_ratio = parsed.notna().mean()
    return bool(parsed_ratio >= 0.8 and string_like_ratio >= 0.4)


def _compute_histogram_bins(question_df: pd.DataFrame) -> list[dict[str, Any]]:
    if question_df.empty or "answer" not in question_df.columns:
        return []

    numeric = pd.to_numeric(question_df["answer"], errors="coerce").dropna()
    if numeric.empty:
        return []

    unique_count = int(numeric.nunique())
    if unique_count <= 6:
        counts = numeric.value_counts().sort_index()
        return [
            {
                "label": _format_numeric_value_label(value),
                "count": int(count),
                "start": float(value),
                "end": float(value),
            }
            for value, count in counts.items()
        ]

    bin_count = min(6, max(4, unique_count))
    histogram = pd.cut(numeric, bins=bin_count, include_lowest=True, duplicates="drop")
    counts = histogram.value_counts().sort_index()
    bins: list[dict[str, Any]] = []
    for interval, count in counts.items():
        left = float(interval.left)
        right = float(interval.right)
        bins.append(
            {
                "label": f"{_format_numeric_value_label(left)}–{_format_numeric_value_label(right)}",
                "count": int(count),
                "start": left,
                "end": right,
            }
        )
    return bins


def _compute_time_series_points(question_df: pd.DataFrame) -> list[dict[str, Any]]:
    if question_df.empty or "answer" not in question_df.columns:
        return []

    parsed = pd.to_datetime(question_df["answer"], errors="coerce")
    if parsed.dropna().empty:
        return []

    series_df = question_df.copy()
    series_df["parsed_answer"] = parsed
    series_df = series_df.dropna(subset=["parsed_answer"])
    if series_df.empty:
        return []

    grouped = (
        series_df.groupby(series_df["parsed_answer"].dt.normalize())
        .size()
        .reset_index(name="count")
        .sort_values("parsed_answer")
    )
    return [
        {
            "label": value.strftime("%Y-%m-%d"),
            "count": int(count),
            "value": value.isoformat(),
        }
        for value, count in grouped.itertuples(index=False, name=None)
    ]


def _build_word_cloud_terms(question_df: pd.DataFrame) -> list[dict[str, Any]]:
    if question_df.empty or "answer" not in question_df.columns:
        return []

    counter: Counter[str] = Counter()
    for raw_answer in question_df["answer"].dropna().astype(str):
        normalized = re.sub(r"[^a-z0-9\s]", " ", raw_answer.lower())
        for token in normalized.split():
            if len(token) < 3 or token.isdigit() or token in _ANALYSIS_STOP_WORDS:
                continue
            counter[token] += 1

    if not counter:
        return []

    terms = counter.most_common(24)
    highest = max(count for _, count in terms)
    return [
        {
            "term": term,
            "count": int(count),
            "weight": round(count / highest, 3) if highest else 0,
        }
        for term, count in terms
    ]


def _build_open_text_quotes(question_df: pd.DataFrame, *, limit: int) -> list[dict[str, Any]]:
    if question_df.empty or "answer" not in question_df.columns:
        return []

    quotes_df = question_df.copy()
    quotes_df["answer"] = quotes_df["answer"].astype(str)
    quotes_df = quotes_df[quotes_df["answer"].str.strip().astype(bool)]
    if quotes_df.empty:
        return []

    subset_columns = [column for column in ["answer"] if column in quotes_df.columns]
    quotes_df = quotes_df.drop_duplicates(subset=subset_columns).head(limit)
    quotes: list[dict[str, Any]] = []
    for _, row in quotes_df.iterrows():
        quotes.append(
            {
                "text": str(row.get("answer") or ""),
                "respondent_id": str(row.get("respondent_id") or "") or None,
                "model": str(row.get("model") or "") or None,
            }
        )
    return quotes


def _format_numeric_value_label(value: float) -> str:
    rounded = round(float(value), 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


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
        for option in all_question_options:
            option_id = str(option.get("id") or "")
            if option_id in filtered_question_ids:
                return option_id
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
        raise LegacyModuleApiError("Product URL autofill failed.") from exc


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
        raise LegacyModuleApiError("Product image analysis failed.") from exc

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
