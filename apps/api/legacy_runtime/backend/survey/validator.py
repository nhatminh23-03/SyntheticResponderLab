"""Validation helpers for normalized survey schemas."""

from __future__ import annotations

from typing import Dict, Union

from backend.schemas import SurveySchema


def validate_survey_schema(schema_or_payload: Union[SurveySchema, Dict]) -> SurveySchema:
	"""Validate and return a `SurveySchema` object.

	This function reuses Pydantic validation rules from `SurveySchema` and adds
	a small duplicate-ID check for cleaner downstream use.
	"""
	if isinstance(schema_or_payload, SurveySchema):
		schema = SurveySchema(**schema_or_payload.model_dump())
	else:
		schema = SurveySchema(**dict(schema_or_payload))

	question_ids = [question.id for question in schema.questions]
	duplicate_ids = {question_id for question_id in question_ids if question_ids.count(question_id) > 1}
	if duplicate_ids:
		duplicates = ", ".join(sorted(duplicate_ids))
		raise ValueError(f"Duplicate question ids found: {duplicates}")

	return schema
