from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.adapters.legacy_backend.domain import (
    build_geography_context,
    build_analysis_view,
    build_insights_view,
    execute_simulation_run,
    execute_stability_check,
    list_model_catalog,
    load_neo_survey_schema_default,
    parse_normalize_validate_survey,
    preview_personas,
    product_image_analysis,
    product_url_autofill,
    validate_audience,
    validate_experiment,
    validate_market,
    validate_product,
)
from src.config.settings import AppSettings
from src.persistence.models import (
    Job,
    PersonaPreviewPersona,
    PersonaPreviewRun,
    Study,
    StudyAsset,
    StudyProductEnrichment,
    StudySectionState,
)
from src.persistence.storage import persist_asset_bytes
from src.schemas.study import (
    CanonicalStudy,
    PersonaPreviewResult,
    ProductEnrichmentSummary,
    ProductEnrichments,
    ProductState,
    StudyDerived,
    StudyModeState,
    StudyOwner,
    AudienceState,
    ExperimentState,
    MarketState,
    SurveyState,
)
from src.services.exceptions import ConflictApiError, NotFoundApiError, UnsupportedMediaTypeApiError, ValidationApiError
from src.services.ids import make_public_id
from src.services.workflow_service import build_workflow


SECTION_KEYS = ("study_mode", "audience", "product", "market", "survey", "experiment")
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
SURVEY_EXTENSIONS = {"md", "docx", "pdf"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_study(
    session: Session,
    settings: AppSettings,
    *,
    study_mode: Optional[str],
    owner_user_id: Optional[str],
    owner_org_id: Optional[str],
) -> CanonicalStudy:
    study = Study(
        public_id=make_public_id("std"),
        owner_user_id=owner_user_id,
        owner_org_id=owner_org_id,
        study_mode=None,
        lifecycle_status="draft",
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(study)
    session.flush()

    for key in SECTION_KEYS:
        session.add(
            StudySectionState(
                study_id=study.id,
                section_key=key,
                status="not_started",
                value_json=None,
                validation_errors_json=None,
                saved_at=None,
                updated_at=utcnow(),
            )
        )

    session.flush()
    if study_mode is not None:
        _validate_study_mode(study_mode)
        _save_study_mode_internal(session, study, study_mode)

    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)
    return serialize_study(session, study)


def get_study_or_404(session: Session, public_id: str) -> Study:
    study = session.scalar(select(Study).where(Study.public_id == public_id))
    if study is None:
        raise NotFoundApiError("Study not found.")
    return study


def serialize_study(session: Session, study: Study) -> CanonicalStudy:
    sections = _get_sections(session, study)
    latest_url = _latest_enrichment(session, study.id, "product_url_autofill")
    latest_image = _latest_enrichment(session, study.id, "product_image_analysis")
    latest_preview = _latest_persona_preview(session, study)
    workflow = build_workflow(study=study, sections=sections, latest_preview=latest_preview)

    return CanonicalStudy(
        study_id=study.public_id,
        lifecycle_status=study.lifecycle_status,
        owner=StudyOwner(owner_user_id=study.owner_user_id, owner_org_id=study.owner_org_id),
        study_mode=StudyModeState(
            status=sections["study_mode"].status,
            value=_section_value_or_none(sections["study_mode"], "study_mode"),
            saved_at=sections["study_mode"].saved_at,
            updated_at=sections["study_mode"].updated_at,
        ),
        audience=AudienceState(
            status=sections["audience"].status,
            value=sections["audience"].value_json,
            saved_at=sections["audience"].saved_at,
            updated_at=sections["audience"].updated_at,
        ),
        product=ProductState(
            status=sections["product"].status,
            value=sections["product"].value_json,
            saved_at=sections["product"].saved_at,
            updated_at=sections["product"].updated_at,
        ),
        market=MarketState(
            status=sections["market"].status,
            value=sections["market"].value_json,
            saved_at=sections["market"].saved_at,
            updated_at=sections["market"].updated_at,
        ),
        survey=_build_survey_state(sections["survey"]),
        experiment=ExperimentState(
            status=sections["experiment"].status,
            value=sections["experiment"].value_json,
            saved_at=sections["experiment"].saved_at,
            updated_at=sections["experiment"].updated_at,
        ),
        product_enrichments=ProductEnrichments(
            latest_url_autofill=_serialize_enrichment(latest_url),
            latest_image_analysis=_serialize_enrichment(latest_image),
        ),
        derived=StudyDerived(
            geography_context=latest_preview.geography_context_json if latest_preview else None,
            workflow=workflow,
            latest_persona_preview=_serialize_persona_preview(latest_preview),
        ),
        created_at=study.created_at,
        updated_at=study.updated_at,
        archived_at=study.archived_at,
    )


def save_study_mode(session: Session, study: Study, study_mode: str) -> CanonicalStudy:
    _validate_study_mode(study_mode)
    _save_study_mode_internal(session, study, study_mode)
    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)
    return serialize_study(session, study)


def save_audience_section(session: Session, settings: AppSettings, study: Study, payload: Dict[str, Any]) -> CanonicalStudy:
    validated = validate_audience(payload, settings.legacy_app_root)
    _save_section(session, study, "audience", validated)
    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)
    return serialize_study(session, study)


def save_product_section(session: Session, settings: AppSettings, study: Study, payload: Dict[str, Any]) -> CanonicalStudy:
    validated = validate_product(payload, settings.legacy_app_root)
    _save_section(session, study, "product", validated)
    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)
    return serialize_study(session, study)


def save_market_section(session: Session, settings: AppSettings, study: Study, payload: Dict[str, Any]) -> CanonicalStudy:
    validated = validate_market(payload, settings.legacy_app_root)
    if not _market_has_content(validated):
        raise ValidationApiError("Market context must include at least one meaningful field.")
    _save_section(session, study, "market", validated)
    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)
    return serialize_study(session, study)


def save_experiment_section(session: Session, settings: AppSettings, study: Study, payload: Dict[str, Any]) -> CanonicalStudy:
    validated = validate_experiment(payload, settings.legacy_app_root)
    _save_section(session, study, "experiment", validated)
    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)
    return serialize_study(session, study)


def handle_product_url_autofill(
    session: Session,
    settings: AppSettings,
    study: Study,
    *,
    url: str,
    apply_to_product: bool,
) -> Dict[str, Any]:
    result = product_url_autofill(settings=settings, url=url)

    text_asset = _create_asset_from_bytes(
        session,
        settings,
        study,
        asset_type="scraped_page_text",
        original_filename="page.txt",
        mime_type="text/plain",
        payload=result["page_text"].encode("utf-8"),
    )

    enrichment = StudyProductEnrichment(
        public_id=make_public_id("pen"),
        study_id=study.id,
        enrichment_type="product_url_autofill",
        status="completed",
        input_url=url,
        source_asset_id=text_asset.id,
        request_json={"apply_to_product": apply_to_product},
        result_json={
            "scraped_text_asset_id": text_asset.public_id,
            "proposed_product_patch": result["product_patch"],
            "warnings": [],
        },
        error_json=None,
        applied_to_product=apply_to_product,
        created_at=utcnow(),
        completed_at=utcnow(),
    )
    session.add(enrichment)
    if apply_to_product:
        _save_section(session, study, "product", result["product_patch"])

    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)
    return {
        "enrichment": _serialize_enrichment(enrichment).model_dump(mode="json"),
        "product": serialize_study(session, study).product.model_dump(mode="json"),
    }


def handle_product_image_analysis(
    session: Session,
    settings: AppSettings,
    study: Study,
    *,
    filename: str,
    content_type: str,
    file_bytes: bytes,
    apply_to_product: bool,
) -> Dict[str, Any]:
    extension = _extension_from_name(filename)
    if extension not in IMAGE_EXTENSIONS:
        raise UnsupportedMediaTypeApiError("Unsupported image type. Please upload jpg, jpeg, or png.")

    image_asset = _create_asset_from_bytes(
        session,
        settings,
        study,
        asset_type="product_image",
        original_filename=filename,
        mime_type=content_type or "application/octet-stream",
        payload=file_bytes,
    )

    result = product_image_analysis(settings=settings, file_bytes=file_bytes)

    enrichment = StudyProductEnrichment(
        public_id=make_public_id("pen"),
        study_id=study.id,
        enrichment_type="product_image_analysis",
        status="completed",
        source_asset_id=image_asset.id,
        request_json={"apply_to_product": apply_to_product},
        result_json={
            "analysis": result["analysis"],
            "proposed_product_patch": result["product_patch"],
        },
        error_json=None,
        applied_to_product=apply_to_product,
        created_at=utcnow(),
        completed_at=utcnow(),
    )
    session.add(enrichment)

    if apply_to_product:
        current_product = _get_sections(session, study)["product"].value_json
        if not current_product:
            raise ConflictApiError("Save the product section before applying image analysis results.")
        merged = dict(current_product)
        merged.update(result["product_patch"])
        validated = validate_product(merged, settings.legacy_app_root)
        _save_section(session, study, "product", validated)

    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)
    return {
        "asset": _asset_payload(image_asset),
        "enrichment": _serialize_enrichment(enrichment).model_dump(mode="json"),
        "product": serialize_study(session, study).product.model_dump(mode="json"),
    }


def handle_survey_upload(
    session: Session,
    settings: AppSettings,
    study: Study,
    *,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> Dict[str, Any]:
    extension = _extension_from_name(filename)
    if extension not in SURVEY_EXTENSIONS:
        raise UnsupportedMediaTypeApiError("Unsupported survey file type. Please upload .md, .docx, or .pdf.")

    asset = _create_asset_from_bytes(
        session,
        settings,
        study,
        asset_type="survey_upload",
        original_filename=filename,
        mime_type=content_type or "application/octet-stream",
        payload=file_bytes,
    )
    schema = parse_normalize_validate_survey(filename, file_bytes, settings.legacy_app_root)
    _save_section(session, study, "survey", schema, source_asset=asset)
    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)

    study_view = serialize_study(session, study)
    return {
        "asset": _asset_payload(asset),
        "survey": study_view.survey.model_dump(mode="json", by_alias=True),
        "workflow": study_view.derived.workflow.model_dump(mode="json"),
    }


def handle_neo_survey_preset(
    session: Session,
    settings: AppSettings,
    study: Study,
) -> Dict[str, Any]:
    if study.study_mode != "neo_smart":
        raise ConflictApiError("Neo survey preset is only available when study_mode is neo_smart.")

    filename, file_bytes, schema = load_neo_survey_schema_default(settings.legacy_app_root)
    asset = _create_asset_from_bytes(
        session,
        settings,
        study,
        asset_type="survey_upload",
        original_filename=filename,
        mime_type="text/markdown",
        payload=file_bytes,
    )
    _save_section(session, study, "survey", schema, source_asset=asset)
    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)

    study_view = serialize_study(session, study)
    return {
        "asset": _asset_payload(asset),
        "survey": study_view.survey.model_dump(mode="json", by_alias=True),
        "workflow": study_view.derived.workflow.model_dump(mode="json"),
    }


def get_workflow(session: Session, study: Study) -> Dict[str, Any]:
    study_view = serialize_study(session, study)
    return study_view.derived.workflow.model_dump(mode="json")


def get_models(settings: AppSettings) -> Dict[str, Any]:
    return list_model_catalog(settings=settings)


def create_persona_preview(
    session: Session,
    settings: AppSettings,
    study: Study,
    *,
    sample_size: int,
    use_grounded_priors: bool,
    use_geography_filtered_priors: bool,
    use_cex_affordability_priors: bool,
    seed: Optional[int],
) -> Dict[str, Any]:
    if sample_size < 1 or sample_size > 50:
        raise ValidationApiError("sample_size must be between 1 and 50.")

    sections = _get_sections(session, study)
    audience = sections["audience"].value_json
    if not audience:
        raise ConflictApiError("Audience must be saved before persona preview.")
    if sections["experiment"].status != "saved":
        raise ConflictApiError("Experiment plan must be saved before persona preview.")

    geography_context = None
    warnings: List[str] = []
    zip_code = audience.get("zip_code")
    if zip_code:
        geography_context = build_geography_context(zip_code, settings)
        source = geography_context.get("source")
        if source and source not in {"hud_local_crosswalk", "hud_zip_crosswalk_api"}:
            warnings.append(f"geography lookup degraded: {source}")

    preview_result = preview_personas(
        settings=settings,
        audience_payload=audience,
        sample_size=sample_size,
        use_grounded_priors=use_grounded_priors,
        use_geography_filtered_priors=use_geography_filtered_priors,
        use_cex_affordability_priors=use_cex_affordability_priors,
        seed=seed,
        geography_context=geography_context,
    )

    if preview_result["generation_mode"] == "heuristic_fallback":
        warnings.append("grounded priors unavailable; using heuristic fallback")
    if sections["study_mode"].status != "saved":
        warnings.append("study mode not saved")
    if sections["product"].status != "saved":
        warnings.append("product not saved")
    if sections["market"].status != "saved":
        warnings.append("market not saved")
    if sections["survey"].status != "saved":
        warnings.append("survey not uploaded")

    preview_run = PersonaPreviewRun(
        public_id=make_public_id("ppr"),
        study_id=study.id,
        status="completed",
        sample_size=sample_size,
        use_grounded_priors=use_grounded_priors,
        use_geography_filtered_priors=use_geography_filtered_priors,
        use_cex_affordability_priors=use_cex_affordability_priors,
        seed=seed,
        generation_mode=preview_result["generation_mode"],
        grounded_priors_available=preview_result["grounded_priors_available"],
        cex_affordability_available=preview_result["cex_affordability_available"],
        geography_context_json=geography_context,
        prior_notes_json=preview_result["prior_notes"],
        warning_messages_json=warnings,
        created_at=utcnow(),
        completed_at=utcnow(),
    )
    session.add(preview_run)
    session.flush()

    for index, persona in enumerate(preview_result["personas"]):
        session.add(
            PersonaPreviewPersona(
                preview_run_id=preview_run.id,
                study_id=study.id,
                row_index=index,
                persona_id=str(persona.get("persona_id", "")),
                fit_tier=persona.get("fit_tier"),
                segment_label=persona.get("segment_label"),
                persona_json=persona,
                created_at=utcnow(),
            )
        )

    study.latest_persona_preview_run_id = preview_run.id
    _touch_study(study)
    _recompute_lifecycle_status(session, study)
    session.commit()
    session.refresh(study)
    study_view = serialize_study(session, study)
    preview_payload = study_view.derived.latest_persona_preview
    return {
        "persona_preview": preview_payload.model_dump(mode="json") if preview_payload else None,
        "workflow": study_view.derived.workflow.model_dump(mode="json"),
    }


def start_simulation_run(
    session: Session,
    settings: AppSettings,
    study: Study,
) -> Dict[str, Any]:
    sections = _get_sections(session, study)
    audience = sections["audience"].value_json
    survey = sections["survey"].value_json
    experiment = sections["experiment"].value_json
    product = sections["product"].value_json if sections["product"].status == "saved" else None
    market = sections["market"].value_json if sections["market"].status == "saved" else None

    if not audience:
        raise ConflictApiError("Audience must be saved before running the study.")
    if not survey:
        raise ConflictApiError("Survey must be saved before running the study.")
    if not experiment:
        raise ConflictApiError("Experiment plan must be saved before running the study.")

    geography_context = None
    geography_warning = None
    zip_code = audience.get("zip_code")
    if zip_code:
        try:
            geography_context = build_geography_context(zip_code, settings)
        except Exception as exc:
            geography_warning = f"Geography lookup degraded: {exc}"

    job = Job(
        public_id=make_public_id("job"),
        study_id=study.id,
        job_type="simulation_run",
        status="running",
        payload_json={
            "audience": audience,
            "survey_title": survey.get("survey_title"),
            "experiment": experiment,
        },
        result_json=None,
        error_json=None,
        queued_at=utcnow(),
        started_at=utcnow(),
    )
    session.add(job)
    session.flush()

    try:
        result = execute_simulation_run(
            settings=settings,
            audience_payload=audience,
            survey_payload=survey,
            experiment_payload=experiment,
            product_payload=product,
            market_payload=market,
            geography_context=geography_context,
        )
        if geography_warning:
            result.setdefault("warnings", []).append(geography_warning)
        job.status = "completed"
        job.result_json = result
        job.error_json = None
        job.completed_at = utcnow()
        _touch_study(study)
        session.commit()
    except Exception as exc:
        job.status = "failed"
        job.error_json = {"message": str(exc)}
        job.completed_at = utcnow()
        _touch_study(study)
        session.commit()
        raise

    study_view = serialize_study(session, study)
    return {
        "simulation_run": _serialize_job(job),
        "workflow": study_view.derived.workflow.model_dump(mode="json"),
    }


def get_latest_simulation_run(session: Session, study: Study) -> Optional[Dict[str, Any]]:
    job = _latest_job(session, study.id, "simulation_run")
    return _serialize_job(job) if job else None


def clear_latest_simulation_runs(session: Session, study: Study) -> Dict[str, Any]:
    jobs = session.scalars(
        select(Job).where(
            Job.study_id == study.id,
            Job.job_type.in_(["simulation_run", "simulation_stability"]),
        )
    ).all()
    cleared = len(jobs)
    for job in jobs:
        session.delete(job)
    if cleared:
        _touch_study(study)
    session.commit()
    return {"cleared": cleared}


def start_stability_check(
    session: Session,
    settings: AppSettings,
    study: Study,
    *,
    repeat_runs: int,
) -> Dict[str, Any]:
    sections = _get_sections(session, study)
    audience = sections["audience"].value_json
    survey = sections["survey"].value_json
    experiment = sections["experiment"].value_json
    product = sections["product"].value_json if sections["product"].status == "saved" else None
    market = sections["market"].value_json if sections["market"].status == "saved" else None

    if not audience or not survey or not experiment:
        raise ConflictApiError("Audience, survey, and experiment must be saved before running a stability check.")

    geography_context = None
    zip_code = audience.get("zip_code")
    if zip_code:
        try:
            geography_context = build_geography_context(zip_code, settings)
        except Exception:
            geography_context = None

    job = Job(
        public_id=make_public_id("job"),
        study_id=study.id,
        job_type="simulation_stability",
        status="running",
        payload_json={"repeat_runs": repeat_runs},
        result_json=None,
        error_json=None,
        queued_at=utcnow(),
        started_at=utcnow(),
    )
    session.add(job)
    session.flush()

    try:
        result = execute_stability_check(
            settings=settings,
            audience_payload=audience,
            survey_payload=survey,
            experiment_payload=experiment,
            product_payload=product,
            market_payload=market,
            geography_context=geography_context,
            repeat_runs=repeat_runs,
        )
        job.status = "completed"
        job.result_json = result
        job.error_json = None
        job.completed_at = utcnow()
        _touch_study(study)
        session.commit()
    except Exception as exc:
        job.status = "failed"
        job.error_json = {"message": str(exc)}
        job.completed_at = utcnow()
        _touch_study(study)
        session.commit()
        raise

    return {"stability_check": _serialize_job(job)}


def get_latest_stability_check(session: Session, study: Study) -> Optional[Dict[str, Any]]:
    job = _latest_job(session, study.id, "simulation_stability")
    return _serialize_job(job) if job else None


def get_analysis_view(
    session: Session,
    settings: AppSettings,
    study: Study,
    *,
    question_id: Optional[str],
    model: Optional[str],
    segment: Optional[str],
    records_limit: int,
    records_offset: int,
    open_text_limit: int,
) -> Dict[str, Any]:
    latest_run = _latest_job(session, study.id, "simulation_run")
    latest_run_payload = latest_run.result_json if latest_run and latest_run.status == "completed" else None

    return build_analysis_view(
        settings=settings,
        study_mode=study.study_mode,
        latest_run_payload=latest_run_payload,
        question_id=question_id,
        model=model,
        segment=segment,
        records_limit=max(1, min(records_limit, 100)),
        records_offset=max(0, records_offset),
        open_text_limit=max(1, min(open_text_limit, 30)),
    )


def get_insights_view(
    session: Session,
    settings: AppSettings,
    study: Study,
) -> Dict[str, Any]:
    latest_run = _latest_job(session, study.id, "simulation_run")
    latest_run_payload = latest_run.result_json if latest_run and latest_run.status == "completed" else None

    return build_insights_view(
        settings=settings,
        study_mode=study.study_mode,
        latest_run_payload=latest_run_payload,
    )


def _validate_study_mode(study_mode: str) -> None:
    candidate = str(study_mode or "").strip().lower()
    if candidate not in {"neo_smart", "general"}:
        raise ValidationApiError("study_mode must be one of: neo_smart, general.")


def _save_study_mode_internal(session: Session, study: Study, study_mode: str) -> None:
    normalized = str(study_mode).strip().lower()
    study.study_mode = normalized
    _save_section(session, study, "study_mode", {"study_mode": normalized})
    _touch_study(study)


def _save_section(
    session: Session,
    study: Study,
    key: str,
    value: Dict[str, Any],
    source_asset: Optional[StudyAsset] = None,
) -> None:
    section = _get_sections(session, study)[key]
    if section.saved_at is None:
        section.saved_at = utcnow()
    section.status = "saved"
    section.value_json = value
    section.validation_errors_json = None
    section.updated_at = utcnow()
    section.source_asset = source_asset
    _touch_study(study)
    session.add(section)


def _touch_study(study: Study) -> None:
    study.updated_at = utcnow()


def _recompute_lifecycle_status(session: Session, study: Study) -> None:
    if study.archived_at is not None:
        study.lifecycle_status = "archived"
        return
    if study.latest_persona_preview_run_id is not None:
        study.lifecycle_status = "persona_previewed"
        return
    sections = _get_sections(session, study)
    if all(sections[key].status == "saved" for key in SECTION_KEYS):
        study.lifecycle_status = "ready_for_persona_preview"
        return
    if any(sections[key].status == "saved" for key in SECTION_KEYS):
        study.lifecycle_status = "setup_in_progress"
        return
    study.lifecycle_status = "draft"


def _get_sections(session: Session, study: Study) -> Dict[str, StudySectionState]:
    rows = session.scalars(select(StudySectionState).where(StudySectionState.study_id == study.id)).all()
    mapping = {row.section_key: row for row in rows}
    for key in SECTION_KEYS:
        if key not in mapping:
            row = StudySectionState(
                study_id=study.id,
                section_key=key,
                status="not_started",
                updated_at=utcnow(),
            )
            session.add(row)
            session.flush()
            mapping[key] = row
    return mapping


def _latest_enrichment(session: Session, study_id, enrichment_type: str) -> Optional[StudyProductEnrichment]:
    return session.scalar(
        select(StudyProductEnrichment)
        .where(
            StudyProductEnrichment.study_id == study_id,
            StudyProductEnrichment.enrichment_type == enrichment_type,
        )
        .order_by(StudyProductEnrichment.created_at.desc())
    )


def _latest_persona_preview(session: Session, study: Study) -> Optional[PersonaPreviewRun]:
    if study.latest_persona_preview_run_id is None:
        return None
    return session.scalar(select(PersonaPreviewRun).where(PersonaPreviewRun.id == study.latest_persona_preview_run_id))


def _latest_job(session: Session, study_id, job_type: str) -> Optional[Job]:
    return session.scalar(
        select(Job)
        .where(Job.study_id == study_id, Job.job_type == job_type)
        .order_by(Job.queued_at.desc())
    )


def _section_value_or_none(section: StudySectionState, key: str) -> Any:
    if section.value_json is None:
        return None
    if key == "study_mode":
        return section.value_json.get("study_mode")
    return section.value_json


def _build_survey_state(section: StudySectionState) -> SurveyState:
    value = section.value_json or None
    source_asset = section.source_asset
    parse_warnings = list(value.get("parse_warnings", [])) if value else []
    question_count = len(value.get("questions", [])) if value else None
    return SurveyState(
        status=section.status,
        source_asset_id=source_asset.public_id if source_asset else None,
        source_filename=source_asset.original_filename if source_asset else None,
        source_format=value.get("source_format") if value else None,
        schema_=value,
        question_count=question_count,
        parse_warnings=parse_warnings,
        saved_at=section.saved_at,
        updated_at=section.updated_at,
    )


def _serialize_enrichment(enrichment: Optional[StudyProductEnrichment]) -> Optional[ProductEnrichmentSummary]:
    if enrichment is None:
        return None
    result = enrichment.result_json or {}
    return ProductEnrichmentSummary(
        enrichment_id=enrichment.public_id,
        status=enrichment.status,
        input_url=enrichment.input_url,
        source_asset_id=enrichment.source_asset.public_id if enrichment.source_asset else None,
        scraped_text_asset_id=result.get("scraped_text_asset_id"),
        analysis=result.get("analysis"),
        proposed_product_patch=result.get("proposed_product_patch"),
        warnings=list(result.get("warnings", [])),
        error=enrichment.error_json,
        applied_to_product=enrichment.applied_to_product,
        created_at=enrichment.created_at,
        completed_at=enrichment.completed_at,
    )


def _serialize_persona_preview(preview: Optional[PersonaPreviewRun]) -> Optional[PersonaPreviewResult]:
    if preview is None:
        return None
    personas = [persona.persona_json for persona in sorted(preview.personas, key=lambda item: item.row_index)]
    return PersonaPreviewResult(
        preview_id=preview.public_id,
        status=preview.status,
        request={
            "sample_size": preview.sample_size,
            "use_grounded_priors": preview.use_grounded_priors,
            "use_geography_filtered_priors": preview.use_geography_filtered_priors,
            "use_cex_affordability_priors": preview.use_cex_affordability_priors,
            "seed": preview.seed,
        },
        generation_mode=preview.generation_mode,
        grounded_priors_available=preview.grounded_priors_available,
        cex_affordability_available=preview.cex_affordability_available,
        geography_context=preview.geography_context_json,
        prior_notes=list(preview.prior_notes_json or []),
        warning_messages=list(preview.warning_messages_json or []),
        personas=personas,
        created_at=preview.created_at,
        completed_at=preview.completed_at,
    )


def _create_asset_from_bytes(
    session: Session,
    settings: AppSettings,
    study: Study,
    *,
    asset_type: str,
    original_filename: str,
    mime_type: str,
    payload: bytes,
) -> StudyAsset:
    public_id = make_public_id("ast")
    storage_key, byte_size, sha256 = persist_asset_bytes(
        settings,
        study_public_id=study.public_id,
        asset_public_id=public_id,
        asset_type=asset_type,
        filename=original_filename,
        payload=payload,
    )
    asset = StudyAsset(
        public_id=public_id,
        study_id=study.id,
        asset_type=asset_type,
        status="available",
        original_filename=original_filename,
        mime_type=mime_type,
        byte_size=byte_size,
        sha256=sha256,
        storage_provider="local_fs",
        storage_key=storage_key,
        metadata_json={},
        created_at=utcnow(),
    )
    session.add(asset)
    session.flush()
    _touch_study(study)
    return asset


def _asset_payload(asset: StudyAsset) -> Dict[str, Any]:
    return {
        "asset_id": asset.public_id,
        "asset_type": asset.asset_type,
        "original_filename": asset.original_filename,
        "mime_type": asset.mime_type,
        "byte_size": asset.byte_size,
    }


def _serialize_job(job: Job) -> Dict[str, Any]:
    return {
        "job_id": job.public_id,
        "job_type": job.job_type,
        "status": job.status,
        "payload": job.payload_json or {},
        "result": job.result_json or None,
        "error": job.error_json or None,
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _extension_from_name(filename: str) -> str:
    return filename.lower().rsplit(".", 1)[-1] if "." in filename else ""


def _market_has_content(payload: Dict[str, Any]) -> bool:
    if payload.get("category") or payload.get("typical_price_band") or payload.get("notes"):
        return True
    if payload.get("direct_competitors"):
        return True
    if payload.get("substitutes") or payload.get("common_expected_features") or payload.get("common_objections"):
        return True
    return False
