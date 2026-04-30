"""Core Pydantic schemas for the scaffolded simulation workflow."""

from datetime import datetime
import re
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


AnswerValue = Union[str, int, float, bool, List[str], None]


class AudienceFilter(BaseModel):
    """User-defined constraints for the target audience to simulate."""

    state: Optional[str] = None
    metro: Optional[str] = None
    zip_code: Optional[str] = None
    age_min: Optional[int] = Field(default=None, ge=0, le=120)
    age_max: Optional[int] = Field(default=None, ge=0, le=120)
    income_min: Optional[int] = Field(default=None, ge=0)
    income_max: Optional[int] = Field(default=None, ge=0)
    homeowner_only: bool = False
    renter_only: bool = False
    household_size_min: Optional[int] = Field(default=None, ge=1)
    household_size_max: Optional[int] = Field(default=None, ge=1)
    work_from_home: Optional[bool] = None
    lifestyle_tags: List[str] = Field(default_factory=list)
    home_type: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("state", "metro", "zip_code", "home_type", "notes", mode="before")
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace and normalize empty strings to None."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("zip_code")
    @classmethod
    def _validate_zip_code(cls, value: Optional[str]) -> Optional[str]:
        """Apply lightweight 5-digit US ZIP validation when ZIP is provided."""
        if value is None:
            return None
        if not re.fullmatch(r"\d{5}", value):
            raise ValueError("zip_code must be a 5-digit US ZIP code (e.g., 94105).")
        return value

    @field_validator("lifestyle_tags", mode="before")
    @classmethod
    def _clean_lifestyle_tags(cls, value: Optional[List[str]]) -> List[str]:
        """Trim tag values and drop empty entries."""
        if value is None:
            return []
        cleaned: List[str] = []
        for tag in value:
            if tag is None:
                continue
            tag_clean = str(tag).strip()
            if tag_clean:
                cleaned.append(tag_clean)
        return cleaned

    @model_validator(mode="after")
    def _validate_ranges_and_exclusivity(self) -> "AudienceFilter":
        """Validate numeric ranges and mutually exclusive ownership flags."""
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise ValueError("age_min cannot be greater than age_max.")

        if self.income_min is not None and self.income_max is not None and self.income_min > self.income_max:
            raise ValueError("income_min cannot be greater than income_max.")

        if (
            self.household_size_min is not None
            and self.household_size_max is not None
            and self.household_size_min > self.household_size_max
        ):
            raise ValueError("household_size_min cannot be greater than household_size_max.")

        if self.homeowner_only and self.renter_only:
            raise ValueError("homeowner_only and renter_only cannot both be true.")

        return self


class GeographyContext(BaseModel):
    """Normalized geography mapping context built from ZIP crosswalk lookups."""

    zip_code: Optional[str] = None
    county_fips: Optional[str] = None
    county_name: Optional[str] = None
    cbsa_code: Optional[str] = None
    cbsa_name: Optional[str] = None
    puma: Optional[str] = None
    tract_code: Optional[str] = None
    source: Optional[str] = "hud_zip_crosswalk"

    @field_validator(
        "zip_code",
        "county_fips",
        "county_name",
        "cbsa_code",
        "cbsa_name",
        "puma",
        "tract_code",
        "source",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace and normalize empty strings to None."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("zip_code")
    @classmethod
    def _validate_zip_code(cls, value: Optional[str]) -> Optional[str]:
        """Apply lightweight 5-digit ZIP validation when ZIP is present."""
        if value is None:
            return None
        if not re.fullmatch(r"\d{5}", value):
            raise ValueError("zip_code must be a 5-digit US ZIP code (e.g., 94105).")
        return value


class PersonaSeed(BaseModel):
    """Structured seed profile sampled from grounding data before LLM enrichment."""

    seed_id: str
    audience_id: str
    source_dataset: str = Field(description="e.g., ACS_PUMS, AHS, blended")
    geography: str
    age: int = Field(ge=0, le=120)
    household_size: int = Field(ge=1)
    income_band: str
    home_type: Optional[str] = None
    ownership_status: Optional[Literal["own", "rent", "other"]] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class PersonaCard(BaseModel):
    """Simulation-ready persona combining grounded features and narrative texture."""

    persona_id: str
    seed_id: str
    display_name: str
    short_bio: str
    demographics: Dict[str, Any] = Field(default_factory=dict)
    psychographics: Dict[str, Any] = Field(default_factory=dict)
    constraints: List[str] = Field(default_factory=list)
    grounding_notes: List[str] = Field(default_factory=list)


class BusinessProductContext(BaseModel):
    """Business and product context for framing synthetic research runs."""

    business_name: Optional[str] = None
    industry: Optional[str] = None
    product_name: Optional[str] = None
    product_type: Optional[str] = None
    product_description: Optional[str] = None
    target_customer: Optional[str] = None
    price_range: Optional[str] = None
    primary_goal: Optional[str] = None
    key_features: List[str] = Field(default_factory=list)
    main_use_cases: List[str] = Field(default_factory=list)
    main_pain_points_solved: List[str] = Field(default_factory=list)
    main_barriers_or_concerns: List[str] = Field(default_factory=list)
    product_image_labels: List[str] = Field(default_factory=list)
    product_image_objects: List[str] = Field(default_factory=list)
    product_image_colors: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @field_validator(
        "business_name",
        "industry",
        "product_name",
        "product_type",
        "product_description",
        "target_customer",
        "price_range",
        "primary_goal",
        "notes",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace and normalize empty strings to None."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator(
        "key_features",
        "main_use_cases",
        "main_pain_points_solved",
        "main_barriers_or_concerns",
        "product_image_labels",
        "product_image_objects",
        "product_image_colors",
        mode="before",
    )
    @classmethod
    def _clean_list_fields(cls, value: Optional[List[str]]) -> List[str]:
        """Trim list values and remove empty entries."""
        if value is None:
            return []
        cleaned: List[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def _validate_minimum_context(self) -> "BusinessProductContext":
        """Require at least product name or description for a valid saved object."""
        if not self.product_name and not self.product_description:
            raise ValueError("Please provide at least product_name or product_description.")
        return self


class ResearchBrief(BaseModel):
    """Researcher intent brief for framing an interview insights session."""

    primary_question: Optional[str] = None
    hypotheses: List[str] = Field(default_factory=list)
    decisions_to_inform: List[str] = Field(default_factory=list)
    focus_fit_tiers: List[Literal["strong", "soft", "latent", "edge"]] = Field(default_factory=list)
    focus_segments: List[str] = Field(default_factory=list)
    known_context: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("primary_question", "known_context", "notes", mode="before")
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("hypotheses", "decisions_to_inform", "focus_segments", mode="before")
    @classmethod
    def _clean_list_fields(cls, value: Optional[List[str]]) -> List[str]:
        if value is None:
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @model_validator(mode="after")
    def _validate_minimum_context(self) -> "ResearchBrief":
        if not self.primary_question and not self.hypotheses:
            raise ValueError("Please provide at least a primary_question or one hypothesis.")
        return self


class CompetitorEntry(BaseModel):
    """Manual competitor entry for simple market framing."""

    name: Optional[str] = None
    product_type: Optional[str] = None
    price_range: Optional[str] = None
    key_features: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)

    @field_validator("name", "product_type", "price_range", mode="before")
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace and normalize empty strings to None."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("key_features", "strengths", "weaknesses", mode="before")
    @classmethod
    def _clean_list_fields(cls, value: Optional[List[str]]) -> List[str]:
        """Trim list values and remove empty entries."""
        if value is None:
            return []
        cleaned: List[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned


class MarketContext(BaseModel):
    """Manual market and competitor context entered by the user."""

    category: Optional[str] = None
    direct_competitors: List[CompetitorEntry] = Field(default_factory=list)
    substitutes: List[str] = Field(default_factory=list)
    typical_price_band: Optional[str] = None
    common_expected_features: List[str] = Field(default_factory=list)
    common_objections: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @field_validator("category", "typical_price_band", "notes", mode="before")
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace and normalize empty strings to None."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("substitutes", "common_expected_features", "common_objections", mode="before")
    @classmethod
    def _clean_list_fields(cls, value: Optional[List[str]]) -> List[str]:
        """Trim list values and remove empty entries."""
        if value is None:
            return []
        cleaned: List[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned


class SurveyQuestion(BaseModel):
    """Single normalized survey question."""

    id: str
    text: str
    question_type: Literal["single_choice", "multi_choice", "likert", "numeric", "open_text"]
    options: List[str] = Field(default_factory=list)
    required: bool = True
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    help_text: Optional[str] = None

    @field_validator("id", "text", "help_text", mode="before")
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace for text-like fields."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("options", mode="before")
    @classmethod
    def _clean_options(cls, value: Optional[List[str]]) -> List[str]:
        """Trim options and remove empty entries."""
        if value is None:
            return []
        cleaned: List[str] = []
        for option in value:
            option_text = str(option).strip()
            if option_text:
                cleaned.append(option_text)
        return cleaned

    @model_validator(mode="after")
    def _validate_question_shape(self) -> "SurveyQuestion":
        """Validate type-specific question requirements."""
        if not self.id:
            raise ValueError("Question id cannot be empty.")
        if not self.text:
            raise ValueError("Question text cannot be empty.")

        if self.question_type in {"single_choice", "multi_choice"} and not self.options:
            raise ValueError("single_choice and multi_choice questions must include options.")

        if self.question_type == "likert":
            if self.min_value is None or self.max_value is None:
                raise ValueError("likert questions must include min_value and max_value.")
            if self.min_value > self.max_value:
                raise ValueError("For likert questions, min_value cannot be greater than max_value.")

        return self


class SurveySchema(BaseModel):
    """Uploaded survey normalized into a stable schema."""

    survey_title: Optional[str] = None
    description: Optional[str] = None
    source_format: Optional[str] = None
    parse_warnings: List[str] = Field(default_factory=list)
    questions: List[SurveyQuestion] = Field(default_factory=list)

    @field_validator("survey_title", "description", "source_format", mode="before")
    @classmethod
    def _strip_schema_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace and normalize empty strings."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("parse_warnings", mode="before")
    @classmethod
    def _clean_parse_warnings(cls, value: Optional[List[str]]) -> List[str]:
        """Normalize warning text entries."""
        if value is None:
            return []
        cleaned: List[str] = []
        for warning in value:
            warning_text = str(warning).strip()
            if warning_text:
                cleaned.append(warning_text)
        return cleaned

    @model_validator(mode="after")
    def _validate_question_count(self) -> "SurveySchema":
        """Require at least one normalized question."""
        if not self.questions:
            raise ValueError("Survey must contain at least 1 question.")
        return self


class ExperimentPlan(BaseModel):
    """Execution settings for a simulation run."""

    sample_size: int = Field(gt=0)
    selected_models: List[str] = Field(default_factory=list)
    experiment_mode: Literal["split", "mirror", "stability"]
    reruns_per_persona: int = Field(default=1, ge=1)
    mirror_personas_across_models: bool = False
    split_across_models: bool = False
    notes: Optional[str] = None

    @field_validator("selected_models", mode="before")
    @classmethod
    def _clean_selected_models(cls, value: Optional[List[str]]) -> List[str]:
        """Trim model names and remove empty entries."""
        if value is None:
            return []

        cleaned: List[str] = []
        for model in value:
            if model is None:
                continue
            model_name = str(model).strip()
            if model_name:
                cleaned.append(model_name)
        return cleaned

    @field_validator("notes", mode="before")
    @classmethod
    def _strip_notes(cls, value: Optional[str]) -> Optional[str]:
        """Trim notes and normalize empty text to None."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def _validate_and_set_mode_flags(self) -> "ExperimentPlan":
        """Validate mode constraints and keep booleans consistent with mode."""
        if not self.selected_models:
            raise ValueError("At least one model must be selected.")

        if self.experiment_mode in {"mirror", "split"} and len(self.selected_models) < 2:
            raise ValueError(f"{self.experiment_mode} mode requires at least 2 selected models.")

        if self.experiment_mode == "stability" and self.reruns_per_persona < 2:
            raise ValueError("stability mode requires reruns_per_persona to be at least 2.")

        if self.experiment_mode == "mirror":
            self.mirror_personas_across_models = True
            self.split_across_models = False
        elif self.experiment_mode == "split":
            self.mirror_personas_across_models = False
            self.split_across_models = True
        else:
            self.mirror_personas_across_models = False
            self.split_across_models = False

        return self


class SimulationRunConfig(BaseModel):
    """Configuration used to start a simulation run."""

    run_id: str
    survey_title: Optional[str] = None
    survey_question_count: int = Field(ge=0)
    sample_size: int = Field(gt=0)
    selected_models: List[str] = Field(default_factory=list)
    experiment_mode: str
    reruns_per_persona: int = Field(default=1, ge=1)
    status: str = "pending"
    notes: Optional[str] = None

    @field_validator("run_id", "survey_title", "experiment_mode", "status", "notes", mode="before")
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace and normalize empty text to None."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("selected_models", mode="before")
    @classmethod
    def _clean_selected_models(cls, value: Optional[List[str]]) -> List[str]:
        """Trim model names and remove empty entries."""
        if value is None:
            return []
        cleaned: List[str] = []
        for item in value:
            model_name = str(item).strip()
            if model_name:
                cleaned.append(model_name)
        return cleaned

    @model_validator(mode="after")
    def _validate_config(self) -> "SimulationRunConfig":
        """Validate required simulation run config shape."""
        if not self.run_id:
            raise ValueError("run_id cannot be empty.")
        if not self.selected_models:
            raise ValueError("selected_models must contain at least one model.")
        if not self.experiment_mode:
            raise ValueError("experiment_mode cannot be empty.")
        return self


class SimulationRunResult(BaseModel):
    """Result summary for a simulation run (mock or real)."""

    run_id: str
    status: str
    total_requested_responses: int = Field(ge=0)
    total_generated_responses: int = Field(ge=0)
    models_used: List[str] = Field(default_factory=list)
    experiment_mode: str
    survey_title: Optional[str] = None
    question_count: int = Field(default=0, ge=0)
    mock_records_generated: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: Optional[str] = None

    @field_validator("run_id", "status", "experiment_mode", "survey_title", "notes", "created_at", mode="before")
    @classmethod
    def _strip_result_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace and normalize empty strings."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("models_used", "mock_records_generated", mode="before")
    @classmethod
    def _clean_list_strings(cls, value: Optional[List[str]]) -> List[str]:
        """Trim string list values and remove empties."""
        if value is None:
            return []
        cleaned: List[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def _validate_result(self) -> "SimulationRunResult":
        """Validate result consistency fields."""
        if not self.run_id:
            raise ValueError("run_id cannot be empty.")
        if not self.status:
            raise ValueError("status cannot be empty.")
        if self.total_generated_responses > self.total_requested_responses:
            raise ValueError("total_generated_responses cannot exceed total_requested_responses.")
        return self


class PersonaProfile(BaseModel):
    """Lightweight persona profile used for deterministic mock simulation realism."""

    persona_id: str
    age_bucket: Optional[str] = None
    income_bucket: Optional[str] = None
    household_size_bucket: Optional[str] = None
    ownership: Optional[str] = None
    home_type: Optional[str] = None
    work_mode: Optional[str] = None
    lifestyle_tags: List[str] = Field(default_factory=list)
    likely_use_case: Optional[str] = None
    likely_barrier: Optional[str] = None
    segment_label: Optional[str] = None
    affordability_pressure: Optional[str] = None
    housing_burden_proxy: Optional[str] = None
    spend_intensity_bucket: Optional[str] = None
    fit_tier: Optional[Literal["strong", "soft", "latent", "edge"]] = None
    awareness_stage: Optional[Literal["aware", "unaware"]] = None

    @field_validator(
        "persona_id",
        "age_bucket",
        "income_bucket",
        "household_size_bucket",
        "ownership",
        "home_type",
        "work_mode",
        "likely_use_case",
        "likely_barrier",
        "segment_label",
        "affordability_pressure",
        "housing_burden_proxy",
        "spend_intensity_bucket",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace and normalize empty text to None."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("lifestyle_tags", mode="before")
    @classmethod
    def _clean_lifestyle_tags(cls, value: Optional[List[str]]) -> List[str]:
        """Trim lifestyle tags and remove empty values."""
        if value is None:
            return []
        cleaned: List[str] = []
        for tag in value:
            tag_text = str(tag).strip()
            if tag_text:
                cleaned.append(tag_text)
        return cleaned

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "PersonaProfile":
        """Ensure required persona id is present."""
        if not self.persona_id:
            raise ValueError("persona_id cannot be empty.")
        return self


class MockResponseRecord(BaseModel):
    """Mock respondent-level record produced by the simulation foundation."""

    respondent_id: str
    model: str
    experiment_mode: str
    survey_title: Optional[str] = None
    question_id: str
    question_text: str
    question_type: str
    answer: Union[str, int, float, List[str], None] = None
    segment_label: Optional[str] = None
    run_id: str

    @field_validator(
        "respondent_id",
        "model",
        "experiment_mode",
        "survey_title",
        "question_id",
        "question_text",
        "question_type",
        "segment_label",
        "run_id",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace and normalize empty text to None."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "MockResponseRecord":
        """Ensure key required fields are present."""
        required_fields = {
            "respondent_id": self.respondent_id,
            "model": self.model,
            "experiment_mode": self.experiment_mode,
            "question_id": self.question_id,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "run_id": self.run_id,
        }
        for field_name, field_value in required_fields.items():
            if not field_value:
                raise ValueError(f"{field_name} cannot be empty.")
        return self


class ResponseRecord(BaseModel):
    """A single question response produced by one persona under one model."""

    response_id: str
    experiment_id: str
    persona_id: str
    model_id: str
    question_id: str
    answer: AnswerValue
    rationale: Optional[str] = None
    segment_labels: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InterviewTranscript(BaseModel):
    """Single synthetic depth-interview result for one persona under one model."""

    interview_id: str
    persona_id: str
    model: str
    # Persona metadata snapshot (denormalised for easy display/export)
    age_bucket: Optional[str] = None
    income_bucket: Optional[str] = None
    ownership: Optional[str] = None
    work_mode: Optional[str] = None
    home_type: Optional[str] = None
    segment_label: Optional[str] = None
    lifestyle_tags: List[str] = Field(default_factory=list)
    affordability_pressure: Optional[str] = None
    fit_tier: Optional[Literal["strong", "soft", "latent", "edge"]] = None
    awareness_stage: Optional[Literal["aware", "unaware"]] = None
    # Answers keyed by question id (e.g. "IQ1", "IQ2", …)
    answers: Dict[str, str] = Field(default_factory=dict)
    generation_timestamp: Optional[str] = None

    @field_validator(
        "interview_id",
        "persona_id",
        "model",
        "age_bucket",
        "income_bucket",
        "ownership",
        "work_mode",
        "home_type",
        "segment_label",
        "affordability_pressure",
        "generation_timestamp",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("lifestyle_tags", mode="before")
    @classmethod
    def _clean_lifestyle_tags(cls, value: Optional[List[str]]) -> List[str]:
        if value is None:
            return []
        return [str(t).strip() for t in value if str(t).strip()]

    @model_validator(mode="after")
    def _validate_required(self) -> "InterviewTranscript":
        if not self.interview_id:
            raise ValueError("interview_id cannot be empty.")
        if not self.persona_id:
            raise ValueError("persona_id cannot be empty.")
        if not self.model:
            raise ValueError("model cannot be empty.")
        return self


class Finding(BaseModel):
    """Evidence-backed summary item produced by analysis."""

    finding_id: str
    experiment_id: str
    title: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: List[str] = Field(default_factory=list)
    impacted_segments: List[str] = Field(default_factory=list)
    impacted_questions: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
