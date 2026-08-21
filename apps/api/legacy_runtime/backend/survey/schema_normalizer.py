"""Normalize raw parsed survey payloads into strict survey schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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

	# Ids the document names for itself are collected up front, because a question that names none is
	# numbered by position and would otherwise be able to take one of them. A Google Forms export opens
	# with an unlabelled "Email*" field, which became Q1 while the survey's own Q1 was still Q1, and the
	# validator rejected the whole upload over a file that was perfectly valid.
	declared_ids = {
		str(raw_question.get("id")).strip()
		for raw_question in raw_questions
		if str(raw_question.get("id") or "").strip()
	}

	normalized_questions: List[SurveyQuestion] = []
	assigned_ids: set = set()
	for index, raw_question in enumerate(raw_questions, start=1):
		normalized = _normalize_question(
			raw_question=raw_question,
			index=index,
			parse_warnings=parse_warnings,
			taken_ids=declared_ids | assigned_ids,
		)
		assigned_ids.add(normalized["id"])
		normalized_questions.append(SurveyQuestion(**normalized))

	return SurveySchema(
		survey_title=raw_payload.get("survey_title"),
		description=raw_payload.get("description"),
		source_format=raw_payload.get("source_format"),
		parse_warnings=parse_warnings,
		questions=normalized_questions,
	)


def _assign_unused_id(index: int, taken_ids: set, question_text: str, parse_warnings: List[str]) -> str:
	"""Name a question the document did not name, without taking an id it uses elsewhere."""
	candidate = f"Q{index}"
	if candidate not in taken_ids:
		return candidate

	# Falling back to a different Q-number would read as a position the question does not occupy, so
	# the generated id says plainly that the document did not provide one.
	fallback = f"UNNAMED_{index}"
	suffix = 1
	while fallback in taken_ids:
		suffix += 1
		fallback = f"UNNAMED_{index}_{suffix}"
	label = question_text[:60] or "an unlabelled question"
	parse_warnings.append(
		f"{candidate} is already used by another question, so \"{label}\" was named {fallback}."
	)
	return fallback


def _normalize_question(
	raw_question: Dict[str, Any],
	index: int,
	parse_warnings: List[str],
	taken_ids: Optional[set] = None,
) -> Dict[str, Any]:
	"""Normalize one raw question dictionary into schema-shaped fields."""
	question_text = str(raw_question.get("text") or "").strip()
	declared_id = str(raw_question.get("id") or "").strip()
	if declared_id:
		question_id = declared_id
	else:
		question_id = _assign_unused_id(index, taken_ids or set(), question_text, parse_warnings)

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
