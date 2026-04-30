"""Normalize raw parsed survey payloads into strict survey schemas."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.schemas import SurveyQuestion, SurveySchema


QUESTION_TYPE_ALIASES = {
	"single": "single_choice",
	"single_choice": "single_choice",
	"radio": "single_choice",
	"multi": "multi_choice",
	"multiple": "multi_choice",
	"multi_choice": "multi_choice",
	"checkbox": "multi_choice",
	"likert": "likert",
	"scale": "likert",
	"numeric": "numeric",
	"number": "numeric",
	"open": "open_text",
	"open_text": "open_text",
	"text": "open_text",
}


def normalize_survey_payload(raw_payload: Dict[str, Any]) -> SurveySchema:
	"""Convert parser output into a validated `SurveySchema`."""
	raw_questions = raw_payload.get("questions", [])
	parse_warnings = list(raw_payload.get("parse_warnings", []))

	normalized_questions: List[SurveyQuestion] = []
	for index, raw_question in enumerate(raw_questions, start=1):
		normalized = _normalize_question(raw_question=raw_question, index=index, parse_warnings=parse_warnings)
		normalized_questions.append(SurveyQuestion(**normalized))

	return SurveySchema(
		survey_title=raw_payload.get("survey_title"),
		description=raw_payload.get("description"),
		source_format=raw_payload.get("source_format"),
		parse_warnings=parse_warnings,
		questions=normalized_questions,
	)


def _normalize_question(raw_question: Dict[str, Any], index: int, parse_warnings: List[str]) -> Dict[str, Any]:
	"""Normalize one raw question dictionary into schema-shaped fields."""
	question_id = str(raw_question.get("id") or f"Q{index}").strip()
	question_text = str(raw_question.get("text") or "").strip()

	raw_type = str(raw_question.get("question_type") or "open_text").strip().lower()
	question_type = QUESTION_TYPE_ALIASES.get(raw_type)
	if question_type is None:
		parse_warnings.append(
			f"Unknown question type '{raw_type}' for {question_id}; defaulted to open_text."
		)
		question_type = "open_text"

	options = raw_question.get("options") or []
	if isinstance(options, str):
		options = [part.strip() for part in options.split("|") if part.strip()]

	return {
		"id": question_id,
		"text": question_text,
		"question_type": question_type,
		"options": options,
		"required": bool(raw_question.get("required", True)),
		"min_value": raw_question.get("min_value"),
		"max_value": raw_question.get("max_value"),
		"help_text": raw_question.get("help_text"),
	}
