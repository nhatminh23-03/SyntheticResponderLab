from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from src.schemas.workflow import WorkflowReadiness


class SectionEnvelope(BaseModel):
    status: str
    saved_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class StudyModeState(SectionEnvelope):
    value: Optional[str] = None


class AudienceState(SectionEnvelope):
    value: Optional[Dict[str, Any]] = None


class ProductState(SectionEnvelope):
    value: Optional[Dict[str, Any]] = None


class MarketState(SectionEnvelope):
    value: Optional[Dict[str, Any]] = None


class SurveyState(SectionEnvelope):
    model_config = ConfigDict(populate_by_name=True)

    source_asset_id: Optional[str] = None
    source_filename: Optional[str] = None
    source_format: Optional[str] = None
    schema_: Optional[Dict[str, Any]] = Field(default=None, alias="schema")
    question_count: Optional[int] = None
    parse_warnings: List[str] = Field(default_factory=list)


class ExperimentState(SectionEnvelope):
    value: Optional[Dict[str, Any]] = None


class ProductEnrichmentSummary(BaseModel):
    enrichment_id: str
    status: str
    input_url: Optional[str] = None
    source_asset_id: Optional[str] = None
    scraped_text_asset_id: Optional[str] = None
    analysis: Optional[Dict[str, Any]] = None
    proposed_product_patch: Optional[Dict[str, Any]] = None
    warnings: List[str] = Field(default_factory=list)
    error: Optional[Dict[str, Any]] = None
    applied_to_product: bool = False
    created_at: datetime
    completed_at: Optional[datetime] = None


class ProductEnrichments(BaseModel):
    latest_url_autofill: Optional[ProductEnrichmentSummary] = None
    latest_image_analysis: Optional[ProductEnrichmentSummary] = None


class PersonaPreviewResult(BaseModel):
    preview_id: str
    status: str
    request: Dict[str, Any]
    generation_mode: Optional[str] = None
    grounded_priors_available: Optional[bool] = None
    cex_affordability_available: Optional[bool] = None
    geography_context: Optional[Dict[str, Any]] = None
    prior_notes: List[Dict[str, Any]] = Field(default_factory=list)
    warning_messages: List[str] = Field(default_factory=list)
    personas: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    completed_at: Optional[datetime] = None


class PromptPreviewResult(BaseModel):
    persona_index: int
    persona_id: Optional[str] = None
    persona_label: Optional[str] = None
    survey_title: Optional[str] = None
    system_instruction: str
    user_instruction: str
    combined_prompt: str


class StudyOwner(BaseModel):
    owner_user_id: Optional[str] = None
    owner_org_id: Optional[str] = None


class StudyDerived(BaseModel):
    geography_context: Optional[Dict[str, Any]] = None
    workflow: WorkflowReadiness
    latest_persona_preview: Optional[PersonaPreviewResult] = None


class CanonicalStudy(BaseModel):
    study_id: str
    lifecycle_status: str
    owner: StudyOwner
    study_mode: StudyModeState
    audience: AudienceState
    product: ProductState
    market: MarketState
    survey: SurveyState
    experiment: ExperimentState
    product_enrichments: ProductEnrichments
    derived: StudyDerived
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None


class StudyCreateRequest(BaseModel):
    study_mode: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_org_id: Optional[str] = None


class StudyModeUpdateRequest(BaseModel):
    study_mode: str


class ProductUrlAutofillRequest(BaseModel):
    url: HttpUrl
    apply_to_product: bool = False


class PersonaPreviewRequest(BaseModel):
    sample_size: int = 12
    use_grounded_priors: bool = True
    use_geography_filtered_priors: bool = True
    use_cex_affordability_priors: bool = True
    seed: Optional[int] = None


class StabilityCheckRequest(BaseModel):
    repeat_runs: int = 3
