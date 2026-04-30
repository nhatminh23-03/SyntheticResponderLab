"""Simple Streamlit session-state storage helpers.

This module intentionally provides only lightweight helpers for the
`audience_filter` object at this stage of the project.
"""

from __future__ import annotations

from typing import Mapping, Optional, Union

import streamlit as st

from backend.schemas import (
	AudienceFilter,
	BusinessProductContext,
	ExperimentPlan,
	GeographyContext,
	InterviewTranscript,
	MarketContext,
	MockResponseRecord,
	PersonaProfile,
	ResearchBrief,
	SimulationRunResult,
	SurveySchema,
)


SESSION_RESEARCH_BRIEF_KEY = "research_brief"
SESSION_INTERVIEW_TRANSCRIPTS_KEY = "interview_transcripts"
SESSION_AUDIENCE_KEY = "audience_filter"
SESSION_EXPERIMENT_KEY = "experiment_plan"
SESSION_BUSINESS_PRODUCT_CONTEXT_KEY = "business_product_context"
SESSION_MARKET_CONTEXT_KEY = "market_context"
SESSION_SURVEY_KEY = "survey_schema"
SESSION_SIMULATION_RESULT_KEY = "simulation_result"
SESSION_MOCK_RESPONSE_RECORDS_KEY = "mock_response_records"
SESSION_PERSONA_PROFILES_KEY = "persona_profiles"
SESSION_GEOGRAPHY_CONTEXT_KEY = "geography_context"
SESSION_STUDY_MODE_KEY = "study_mode"

STUDY_MODE_NEO_SMART = "neo_smart"
STUDY_MODE_GENERAL = "general"
VALID_STUDY_MODES = {STUDY_MODE_NEO_SMART, STUDY_MODE_GENERAL}


def save_study_mode(study_mode: str) -> str:
	"""Save selected study mode in session state.

	Valid values:
	- neo_smart
	- general
	"""
	candidate = str(study_mode or "").strip().lower()
	if candidate not in VALID_STUDY_MODES:
		raise ValueError(f"Invalid study_mode: {study_mode}")

	st.session_state[SESSION_STUDY_MODE_KEY] = candidate
	return candidate


def load_study_mode() -> Optional[str]:
	"""Load selected study mode from session state."""
	raw = st.session_state.get(SESSION_STUDY_MODE_KEY)
	if raw is None:
		return None
	candidate = str(raw).strip().lower()
	if candidate not in VALID_STUDY_MODES:
		return None
	return candidate


def save_audience_filter(audience_filter: Union[AudienceFilter, Mapping]) -> AudienceFilter:
	"""Validate and save an audience filter to Streamlit session state.

	Accepts either an `AudienceFilter` instance or a dictionary-like object.
	Returns the validated `AudienceFilter` instance that was saved.
	"""
	if isinstance(audience_filter, AudienceFilter):
		validated = audience_filter
	else:
		validated = AudienceFilter(**dict(audience_filter))

	st.session_state[SESSION_AUDIENCE_KEY] = validated.model_dump()
	return validated


def load_audience_filter() -> Optional[AudienceFilter]:
	"""Load a validated audience filter from session state.

	Returns:
		AudienceFilter if valid data exists, otherwise None.

	Notes:
		If the stored payload is malformed or invalid, this function fails
		safely by returning None.
	"""
	raw = st.session_state.get(SESSION_AUDIENCE_KEY)
	if raw is None:
		return None

	try:
		if isinstance(raw, AudienceFilter):
			return raw
		if isinstance(raw, Mapping):
			return AudienceFilter(**dict(raw))
	except Exception:
		return None

	return None


def clear_audience_filter() -> None:
	"""Remove the saved audience filter from session state."""
	st.session_state.pop(SESSION_AUDIENCE_KEY, None)


def has_audience_filter() -> bool:
	"""Return True only when a valid saved audience filter exists."""
	return load_audience_filter() is not None


def save_geography_context(geography_context: Union[GeographyContext, Mapping]) -> GeographyContext:
	"""Validate and save geography context to Streamlit session state."""
	if isinstance(geography_context, GeographyContext):
		validated = geography_context
	else:
		validated = GeographyContext(**dict(geography_context))

	st.session_state[SESSION_GEOGRAPHY_CONTEXT_KEY] = validated.model_dump()
	return validated


def load_geography_context() -> Optional[GeographyContext]:
	"""Load validated geography context from session state."""
	raw = st.session_state.get(SESSION_GEOGRAPHY_CONTEXT_KEY)
	if raw is None:
		return None

	try:
		if isinstance(raw, GeographyContext):
			return raw
		if isinstance(raw, Mapping):
			return GeographyContext(**dict(raw))
	except Exception:
		return None

	return None


def clear_geography_context() -> None:
	"""Remove saved geography context from session state."""
	st.session_state.pop(SESSION_GEOGRAPHY_CONTEXT_KEY, None)


def has_geography_context() -> bool:
	"""Return True only when valid geography context exists."""
	return load_geography_context() is not None


def save_experiment_plan(experiment_plan: Union[ExperimentPlan, Mapping]) -> ExperimentPlan:
	"""Validate and save an experiment plan to Streamlit session state.

	Accepts either an `ExperimentPlan` instance or a dictionary-like object.
	Returns the validated `ExperimentPlan` instance that was saved.
	"""
	if isinstance(experiment_plan, ExperimentPlan):
		validated = experiment_plan
	else:
		validated = ExperimentPlan(**dict(experiment_plan))

	st.session_state[SESSION_EXPERIMENT_KEY] = validated.model_dump()
	return validated


def load_experiment_plan() -> Optional[ExperimentPlan]:
	"""Load a validated experiment plan from session state.

	Returns:
		ExperimentPlan if valid data exists, otherwise None.

	Notes:
		If the stored payload is malformed or invalid, this function fails
		safely by returning None.
	"""
	raw = st.session_state.get(SESSION_EXPERIMENT_KEY)
	if raw is None:
		return None

	try:
		if isinstance(raw, ExperimentPlan):
			return raw
		if isinstance(raw, Mapping):
			return ExperimentPlan(**dict(raw))
	except Exception:
		return None

	return None


def clear_experiment_plan() -> None:
	"""Remove the saved experiment plan from session state."""
	st.session_state.pop(SESSION_EXPERIMENT_KEY, None)


def has_experiment_plan() -> bool:
	"""Return True only when a valid saved experiment plan exists."""
	return load_experiment_plan() is not None


def save_business_product_context(
	business_product_context: Union[BusinessProductContext, Mapping],
) -> BusinessProductContext:
	"""Validate and save business/product context to Streamlit session state."""
	if isinstance(business_product_context, BusinessProductContext):
		validated = business_product_context
	else:
		validated = BusinessProductContext(**dict(business_product_context))

	st.session_state[SESSION_BUSINESS_PRODUCT_CONTEXT_KEY] = validated.model_dump()
	return validated


def load_business_product_context() -> Optional[BusinessProductContext]:
	"""Load validated business/product context from session state."""
	raw = st.session_state.get(SESSION_BUSINESS_PRODUCT_CONTEXT_KEY)
	if raw is None:
		return None

	try:
		if isinstance(raw, BusinessProductContext):
			return raw
		if isinstance(raw, Mapping):
			return BusinessProductContext(**dict(raw))
	except Exception:
		return None

	return None


def clear_business_product_context() -> None:
	"""Remove saved business/product context from session state."""
	st.session_state.pop(SESSION_BUSINESS_PRODUCT_CONTEXT_KEY, None)


def has_business_product_context() -> bool:
	"""Return True only when valid business/product context exists."""
	return load_business_product_context() is not None


def save_market_context(market_context: Union[MarketContext, Mapping]) -> MarketContext:
	"""Validate and save market context to Streamlit session state."""
	if isinstance(market_context, MarketContext):
		validated = market_context
	else:
		validated = MarketContext(**dict(market_context))

	st.session_state[SESSION_MARKET_CONTEXT_KEY] = validated.model_dump()
	return validated


def load_market_context() -> Optional[MarketContext]:
	"""Load validated market context from session state."""
	raw = st.session_state.get(SESSION_MARKET_CONTEXT_KEY)
	if raw is None:
		return None

	try:
		if isinstance(raw, MarketContext):
			return raw
		if isinstance(raw, Mapping):
			return MarketContext(**dict(raw))
	except Exception:
		return None

	return None


def clear_market_context() -> None:
	"""Remove saved market context from session state."""
	st.session_state.pop(SESSION_MARKET_CONTEXT_KEY, None)


def has_market_context() -> bool:
	"""Return True only when valid market context exists."""
	return load_market_context() is not None


def save_survey_schema(survey_schema: Union[SurveySchema, Mapping]) -> SurveySchema:
	"""Validate and save a survey schema to Streamlit session state.

	Accepts either a `SurveySchema` instance or a dictionary-like object.
	Returns the validated `SurveySchema` instance that was saved.
	"""
	if isinstance(survey_schema, SurveySchema):
		validated = survey_schema
	else:
		validated = SurveySchema(**dict(survey_schema))

	st.session_state[SESSION_SURVEY_KEY] = validated.model_dump()
	return validated


def load_survey_schema() -> Optional[SurveySchema]:
	"""Load a validated survey schema from session state.

	Returns:
		SurveySchema if valid data exists, otherwise None.

	Notes:
		If the stored payload is malformed or invalid, this function fails
		safely by returning None.
	"""
	raw = st.session_state.get(SESSION_SURVEY_KEY)
	if raw is None:
		return None

	try:
		if isinstance(raw, SurveySchema):
			return raw
		if isinstance(raw, Mapping):
			return SurveySchema(**dict(raw))
	except Exception:
		return None

	return None


def clear_survey_schema() -> None:
	"""Remove the saved survey schema from session state."""
	st.session_state.pop(SESSION_SURVEY_KEY, None)


def has_survey_schema() -> bool:
	"""Return True only when a valid saved survey schema exists."""
	return load_survey_schema() is not None


def save_simulation_result(simulation_result: Union[SimulationRunResult, Mapping]) -> SimulationRunResult:
	"""Validate and save a simulation result to Streamlit session state.

	Accepts either a `SimulationRunResult` instance or a dictionary-like object.
	Returns the validated `SimulationRunResult` instance that was saved.
	"""
	if isinstance(simulation_result, SimulationRunResult):
		validated = simulation_result
	else:
		validated = SimulationRunResult(**dict(simulation_result))

	st.session_state[SESSION_SIMULATION_RESULT_KEY] = validated.model_dump()
	return validated


def load_simulation_result() -> Optional[SimulationRunResult]:
	"""Load a validated simulation result from session state.

	Returns:
		SimulationRunResult if valid data exists, otherwise None.

	Notes:
		If the stored payload is malformed or invalid, this function fails
		safely by returning None.
	"""
	raw = st.session_state.get(SESSION_SIMULATION_RESULT_KEY)
	if raw is None:
		return None

	try:
		if isinstance(raw, SimulationRunResult):
			return raw
		if isinstance(raw, Mapping):
			return SimulationRunResult(**dict(raw))
	except Exception:
		return None

	return None


def clear_simulation_result() -> None:
	"""Remove the saved simulation result from session state."""
	st.session_state.pop(SESSION_SIMULATION_RESULT_KEY, None)


def has_simulation_result() -> bool:
	"""Return True only when a valid saved simulation result exists."""
	return load_simulation_result() is not None


def save_mock_response_records(
	mock_response_records: Union[list[MockResponseRecord], list[Mapping], tuple],
) -> list[MockResponseRecord]:
	"""Validate and save mock response records to Streamlit session state.

	Accepts a list of `MockResponseRecord` instances or dictionary-like payloads.
	Returns the validated list that was saved.
	"""
	validated_records: list[MockResponseRecord] = []
	for record in mock_response_records:
		if isinstance(record, MockResponseRecord):
			validated_records.append(record)
		else:
			validated_records.append(MockResponseRecord(**dict(record)))

	st.session_state[SESSION_MOCK_RESPONSE_RECORDS_KEY] = [record.model_dump() for record in validated_records]
	return validated_records


def load_mock_response_records() -> list[MockResponseRecord]:
	"""Load validated mock response records from session state.

	Returns:
		A list of `MockResponseRecord`. Returns an empty list on missing/invalid
		stored payloads to fail safely.
	"""
	raw = st.session_state.get(SESSION_MOCK_RESPONSE_RECORDS_KEY)
	if raw is None:
		return []

	try:
		if isinstance(raw, list):
			validated = []
			for item in raw:
				if isinstance(item, MockResponseRecord):
					validated.append(item)
				elif isinstance(item, Mapping):
					validated.append(MockResponseRecord(**dict(item)))
				else:
					return []
			return validated
	except Exception:
		return []

	return []


def clear_mock_response_records() -> None:
	"""Remove saved mock response records from session state."""
	st.session_state.pop(SESSION_MOCK_RESPONSE_RECORDS_KEY, None)


def has_mock_response_records() -> bool:
	"""Return True only when at least one valid mock response record exists."""
	return len(load_mock_response_records()) > 0


def save_persona_profiles(
	persona_profiles: Union[list[PersonaProfile], list[Mapping], tuple],
) -> list[PersonaProfile]:
	"""Validate and save persona profiles to Streamlit session state."""
	validated_profiles: list[PersonaProfile] = []
	for profile in persona_profiles:
		if isinstance(profile, PersonaProfile):
			validated_profiles.append(profile)
		else:
			validated_profiles.append(PersonaProfile(**dict(profile)))

	st.session_state[SESSION_PERSONA_PROFILES_KEY] = [profile.model_dump() for profile in validated_profiles]
	return validated_profiles


def load_persona_profiles() -> list[PersonaProfile]:
	"""Load validated persona profiles from session state."""
	raw = st.session_state.get(SESSION_PERSONA_PROFILES_KEY)
	if raw is None:
		return []

	try:
		if isinstance(raw, list):
			validated: list[PersonaProfile] = []
			for item in raw:
				if isinstance(item, PersonaProfile):
					validated.append(item)
				elif isinstance(item, Mapping):
					validated.append(PersonaProfile(**dict(item)))
				else:
					return []
			return validated
	except Exception:
		return []

	return []


def clear_persona_profiles() -> None:
	"""Remove saved persona profiles from session state."""
	st.session_state.pop(SESSION_PERSONA_PROFILES_KEY, None)


def has_persona_profiles() -> bool:
	"""Return True only when at least one valid persona profile exists."""
	return len(load_persona_profiles()) > 0


def save_interview_transcripts(
	transcripts: Union[list[InterviewTranscript], list[Mapping], tuple],
) -> list[InterviewTranscript]:
	"""Validate and save interview transcripts to Streamlit session state."""
	validated: list[InterviewTranscript] = []
	for t in transcripts:
		if isinstance(t, InterviewTranscript):
			validated.append(t)
		else:
			validated.append(InterviewTranscript(**dict(t)))
	st.session_state[SESSION_INTERVIEW_TRANSCRIPTS_KEY] = [t.model_dump() for t in validated]
	return validated


def load_interview_transcripts() -> list[InterviewTranscript]:
	"""Load validated interview transcripts from session state."""
	raw = st.session_state.get(SESSION_INTERVIEW_TRANSCRIPTS_KEY)
	if raw is None:
		return []
	try:
		if isinstance(raw, list):
			validated: list[InterviewTranscript] = []
			for item in raw:
				if isinstance(item, InterviewTranscript):
					validated.append(item)
				elif isinstance(item, Mapping):
					validated.append(InterviewTranscript(**dict(item)))
				else:
					return []
			return validated
	except Exception:
		return []
	return []


def clear_interview_transcripts() -> None:
	"""Remove saved interview transcripts from session state."""
	st.session_state.pop(SESSION_INTERVIEW_TRANSCRIPTS_KEY, None)


def has_interview_transcripts() -> bool:
	"""Return True only when at least one valid interview transcript exists."""
	return len(load_interview_transcripts()) > 0


def save_research_brief(research_brief: Union[ResearchBrief, Mapping]) -> ResearchBrief:
	"""Validate and save a research brief to Streamlit session state."""
	if isinstance(research_brief, ResearchBrief):
		validated = research_brief
	else:
		validated = ResearchBrief(**dict(research_brief))

	st.session_state[SESSION_RESEARCH_BRIEF_KEY] = validated.model_dump()
	return validated


def load_research_brief() -> Optional[ResearchBrief]:
	"""Load validated research brief from session state."""
	raw = st.session_state.get(SESSION_RESEARCH_BRIEF_KEY)
	if raw is None:
		return None

	try:
		if isinstance(raw, ResearchBrief):
			return raw
		if isinstance(raw, Mapping):
			return ResearchBrief(**dict(raw))
	except Exception:
		return None

	return None


def clear_research_brief() -> None:
	"""Remove saved research brief from session state."""
	st.session_state.pop(SESSION_RESEARCH_BRIEF_KEY, None)


def has_research_brief() -> bool:
	"""Return True only when a valid saved research brief exists."""
	return load_research_brief() is not None
