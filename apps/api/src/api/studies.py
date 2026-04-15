from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from src.api.dependencies import get_db_session, get_settings
from src.api.errors import response_envelope
from src.config.settings import AppSettings
from src.schemas.study import (
    InterviewChatRequest,
    PersonaPreviewRequest,
    ProductUrlAutofillRequest,
    StabilityCheckRequest,
    StudyCreateRequest,
    StudyModeUpdateRequest,
)
from src.services.study_service import (
    bootstrap_neo_demo_study,
    clear_latest_simulation_runs,
    create_persona_preview,
    create_study,
    get_latest_simulation_run,
    get_latest_stability_check,
    get_analysis_view,
    get_insights_view,
    get_study_or_404,
    get_models,
    get_workflow,
    handle_neo_survey_preset,
    handle_product_image_analysis,
    handle_product_url_autofill,
    handle_survey_upload,
    save_audience_section,
    save_experiment_section,
    save_market_section,
    save_product_section,
    save_study_mode,
    serialize_study,
    start_simulation_run,
    start_stability_check,
)
from src.services.interview_service import (
    continue_interview_chat,
    get_interview_synthesis,
    save_interview_synthesis_config,
    start_interview_run,
    get_latest_interview_run,
    get_research_brief,
    save_research_brief,
    get_interview_insights,
)


router = APIRouter(tags=["studies"])


@router.get("/api/v1/models")
def models_endpoint(
    request: Request,
    settings: AppSettings = Depends(get_settings),
):
    return response_envelope(request, get_models(settings))


@router.post("/api/v1/studies")
def create_study_endpoint(
    request: Request,
    payload: Optional[StudyCreateRequest] = Body(default=None),
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    body = payload or StudyCreateRequest()
    study = create_study(
        db,
        settings,
        study_mode=body.study_mode,
        owner_user_id=body.owner_user_id,
        owner_org_id=body.owner_org_id,
    )
    return response_envelope(request, {"study": study.model_dump(mode="json", by_alias=True)})


@router.get("/api/v1/studies/{study_id}")
def get_study_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
):
    study = get_study_or_404(db, study_id)
    return response_envelope(
        request,
        {"study": serialize_study(db, study).model_dump(mode="json", by_alias=True)},
    )


@router.patch("/api/v1/studies/{study_id}/study-mode")
def patch_study_mode_endpoint(
    study_id: str,
    payload: StudyModeUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
):
    study = get_study_or_404(db, study_id)
    result = save_study_mode(db, study, payload.study_mode)
    return response_envelope(
        request,
        {
            "study_mode": result.study_mode.model_dump(mode="json"),
            "study_lifecycle_status": result.lifecycle_status,
        },
    )


@router.post("/api/v1/studies/{study_id}/study-mode/bootstrap/neo")
def bootstrap_neo_demo_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = bootstrap_neo_demo_study(db, settings, study)
    return response_envelope(
        request,
        {"study": result.model_dump(mode="json", by_alias=True)},
    )


@router.patch("/api/v1/studies/{study_id}/audience")
def patch_audience_endpoint(
    study_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = save_audience_section(db, settings, study, payload)
    return response_envelope(
        request,
        {
            "audience": result.audience.model_dump(mode="json"),
            "workflow": result.derived.workflow.model_dump(mode="json"),
        },
    )


@router.patch("/api/v1/studies/{study_id}/product")
def patch_product_endpoint(
    study_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = save_product_section(db, settings, study, payload)
    return response_envelope(
        request,
        {
            "product": result.product.model_dump(mode="json"),
            "workflow": result.derived.workflow.model_dump(mode="json"),
        },
    )


@router.post("/api/v1/studies/{study_id}/product/url-autofill")
def product_url_autofill_endpoint(
    study_id: str,
    payload: ProductUrlAutofillRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = handle_product_url_autofill(
        db,
        settings,
        study,
        url=str(payload.url),
        apply_to_product=payload.apply_to_product,
    )
    return response_envelope(request, result)


@router.post("/api/v1/studies/{study_id}/product/image-analysis")
async def product_image_analysis_endpoint(
    study_id: str,
    request: Request,
    file: UploadFile = File(...),
    apply_to_product: bool = Form(False),
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    payload = await file.read()
    result = handle_product_image_analysis(
        db,
        settings,
        study,
        filename=file.filename or "upload.bin",
        content_type=file.content_type or "application/octet-stream",
        file_bytes=payload,
        apply_to_product=apply_to_product,
    )
    return response_envelope(request, result)


@router.patch("/api/v1/studies/{study_id}/market")
def patch_market_endpoint(
    study_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = save_market_section(db, settings, study, payload)
    return response_envelope(
        request,
        {
            "market": result.market.model_dump(mode="json"),
            "workflow": result.derived.workflow.model_dump(mode="json"),
        },
    )


@router.post("/api/v1/studies/{study_id}/survey/upload")
async def survey_upload_endpoint(
    study_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    payload = await file.read()
    result = handle_survey_upload(
        db,
        settings,
        study,
        filename=file.filename or "upload.bin",
        content_type=file.content_type or "application/octet-stream",
        file_bytes=payload,
    )
    return response_envelope(request, result)


@router.post("/api/v1/studies/{study_id}/survey/preset/neo")
def neo_survey_preset_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = handle_neo_survey_preset(db, settings, study)
    return response_envelope(request, result)


@router.patch("/api/v1/studies/{study_id}/experiment")
def patch_experiment_endpoint(
    study_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = save_experiment_section(db, settings, study, payload)
    return response_envelope(
        request,
        {
            "experiment": result.experiment.model_dump(mode="json"),
            "workflow": result.derived.workflow.model_dump(mode="json"),
        },
    )


@router.get("/api/v1/studies/{study_id}/workflow")
def workflow_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
):
    study = get_study_or_404(db, study_id)
    return response_envelope(request, {"workflow": get_workflow(db, study)})


@router.get("/api/v1/studies/{study_id}/analysis")
def analysis_endpoint(
    study_id: str,
    request: Request,
    question_id: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    segment: Optional[str] = Query(default=None),
    records_limit: int = Query(default=12),
    records_offset: int = Query(default=0),
    open_text_limit: int = Query(default=10),
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    return response_envelope(
        request,
        {
            "analysis": get_analysis_view(
                db,
                settings,
                study,
                question_id=question_id,
                model=model,
                segment=segment,
                records_limit=records_limit,
                records_offset=records_offset,
                open_text_limit=open_text_limit,
            )
        },
    )


@router.get("/api/v1/studies/{study_id}/insights")
def insights_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    return response_envelope(
        request,
        {
            "insights": get_insights_view(
                db,
                settings,
                study,
            )
        },
    )


@router.post("/api/v1/studies/{study_id}/personas/preview")
def persona_preview_endpoint(
    study_id: str,
    payload: PersonaPreviewRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = create_persona_preview(
        db,
        settings,
        study,
        sample_size=payload.sample_size,
        use_grounded_priors=payload.use_grounded_priors,
        use_geography_filtered_priors=payload.use_geography_filtered_priors,
        use_cex_affordability_priors=payload.use_cex_affordability_priors,
        seed=payload.seed,
    )
    return response_envelope(request, result)


@router.post("/api/v1/studies/{study_id}/simulation-runs")
def start_simulation_run_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = start_simulation_run(db, settings, study)
    return response_envelope(request, result)


@router.get("/api/v1/studies/{study_id}/simulation-runs/latest")
def latest_simulation_run_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
):
    study = get_study_or_404(db, study_id)
    result = get_latest_simulation_run(db, study)
    return response_envelope(request, {"simulation_run": result})


@router.delete("/api/v1/studies/{study_id}/simulation-runs/latest")
def clear_latest_simulation_run_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
):
    study = get_study_or_404(db, study_id)
    result = clear_latest_simulation_runs(db, study)
    return response_envelope(request, result)


@router.post("/api/v1/studies/{study_id}/simulation-runs/stability")
def start_stability_check_endpoint(
    study_id: str,
    payload: StabilityCheckRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = start_stability_check(
        db,
        settings,
        study,
        repeat_runs=payload.repeat_runs,
    )
    return response_envelope(request, result)


@router.get("/api/v1/studies/{study_id}/simulation-runs/stability/latest")
def latest_stability_check_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
):
    study = get_study_or_404(db, study_id)
    result = get_latest_stability_check(db, study)
    return response_envelope(request, {"stability_check": result})


# ---------------------------------------------------------------------------
# Interview endpoints
# ---------------------------------------------------------------------------

@router.get("/api/v1/studies/{study_id}/interview/synthesis")
def get_interview_synthesis_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = get_interview_synthesis(db, study)
    return response_envelope(request, {"interview_synthesis": result})


@router.patch("/api/v1/studies/{study_id}/interview/synthesis")
def patch_interview_synthesis_endpoint(
    study_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = save_interview_synthesis_config(db, study, payload)
    return response_envelope(request, {"interview_synthesis": result})


@router.post("/api/v1/studies/{study_id}/interview/runs")
def start_interview_run_endpoint(
    study_id: str,
    request: Request,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = start_interview_run(db, settings, study, payload or {})
    return response_envelope(request, {"interview_run": result})


@router.get("/api/v1/studies/{study_id}/interview/runs/latest")
def latest_interview_run_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
):
    study = get_study_or_404(db, study_id)
    result = get_latest_interview_run(db, study)
    return response_envelope(request, {"interview_run": result})


@router.get("/api/v1/studies/{study_id}/interview/brief")
def get_research_brief_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
):
    study = get_study_or_404(db, study_id)
    result = get_research_brief(db, study)
    return response_envelope(request, {"research_brief": result})


@router.patch("/api/v1/studies/{study_id}/interview/brief")
def patch_research_brief_endpoint(
    study_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db_session),
):
    study = get_study_or_404(db, study_id)
    result = save_research_brief(db, study, payload)
    return response_envelope(request, {"research_brief": result})


@router.get("/api/v1/studies/{study_id}/interview/insights")
def interview_insights_endpoint(
    study_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = get_interview_insights(db, settings, study)
    return response_envelope(request, {"interview_insights": result})


@router.post("/api/v1/studies/{study_id}/interview/chat")
def interview_chat_endpoint(
    study_id: str,
    payload: InterviewChatRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: AppSettings = Depends(get_settings),
):
    study = get_study_or_404(db, study_id)
    result = continue_interview_chat(db, settings, study, payload.model_dump())
    return response_envelope(request, {"interview_chat": result})
