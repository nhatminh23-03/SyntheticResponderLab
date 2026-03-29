from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence


_CONTROL_LINE_RE = re.compile(r"^\s*\[")
_TRAILING_TAG_RE = re.compile(r"\s*\[[^\]]+\]")
_GENERIC_CONCEPT_PROMPTS = {
    "How appealing is this concept to you personally?",
    "If the Tahoe Mini were marketed this way, how likely would you be to purchase it?",
}


def parse_aytm_style_docx_to_validated_schema(*, text: str, validator_module) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("DOCX parsing extracted no readable text.")

    survey_title = _clean_text(lines[0])
    parse_warnings = [
        "DOCX fallback parser used because the legacy parser interpreted AYTM answer-scale rows as duplicate question ids.",
        "Question ids were regenerated sequentially from the DOCX structure for API compatibility.",
    ]

    questions: List[Dict[str, Any]] = []
    current_concept: Optional[str] = None
    question_number = 0
    index = 0

    while index < len(lines):
        line = lines[index]
        lowered = line.lower()

        if lowered.startswith("order details"):
            break

        if _is_control_line(line):
            if "[instruction]" in lowered:
                current_concept = _extract_concept_label(lines, index + 1)
                index += 1
                continue

            if "[grid]" in lowered or "[sliders]" in lowered:
                question_number += 1
                generated, index = _parse_matrix_block(
                    lines=lines,
                    start_index=index,
                    question_number=question_number,
                    parse_warnings=parse_warnings,
                )
                if generated:
                    questions.extend(generated)
                    continue
                question_number -= 1

            if "[checkboxes]" in lowered:
                question_number += 1
                question, index = _parse_choice_block(
                    lines=lines,
                    start_index=index,
                    question_number=question_number,
                    current_concept=current_concept,
                    multi_choice=True,
                )
                if question is not None:
                    questions.append(question)
                    continue
                question_number -= 1

            if "[radio buttons]" in lowered:
                question_number += 1
                question, index = _parse_choice_block(
                    lines=lines,
                    start_index=index,
                    question_number=question_number,
                    current_concept=current_concept,
                    multi_choice=False,
                )
                if question is not None:
                    questions.append(question)
                    continue
                question_number -= 1

            if "[open ended]" in lowered:
                question_number += 1
                question, index = _parse_open_text_block(
                    lines=lines,
                    start_index=index,
                    question_number=question_number,
                    current_concept=current_concept,
                )
                if question is not None:
                    questions.append(question)
                    continue
                question_number -= 1

        index += 1

    if not questions:
        raise ValueError("DOCX fallback parser could not identify any survey questions.")

    validated = validator_module.validate_survey_schema(
        {
            "survey_title": survey_title,
            "description": None,
            "source_format": "docx",
            "parse_warnings": parse_warnings,
            "questions": questions,
        }
    )
    return validated.model_dump()


def _parse_choice_block(
    *,
    lines: Sequence[str],
    start_index: int,
    question_number: int,
    current_concept: Optional[str],
    multi_choice: bool,
) -> tuple[Optional[Dict[str, Any]], int]:
    index = start_index + 1
    prompt_lines: List[str] = []

    while index < len(lines):
        line = lines[index]
        if _is_control_line(line):
            break
        if _is_answer_options_header(line):
            break
        prompt_lines.append(line)
        index += 1

    if not prompt_lines:
        return None, index

    prompt = _compose_question_text(prompt_lines, current_concept)

    options: List[str] = []
    if index < len(lines) and _is_answer_options_header(lines[index]):
        index += 1
        while index < len(lines):
            option_line = lines[index]
            if _is_control_line(option_line) or option_line.lower().startswith("order details"):
                break
            options.append(_clean_option(option_line))
            index += 1

    scale = _extract_numeric_scale(options)
    if scale is not None:
        return (
            {
                "id": f"Q{question_number}",
                "text": prompt,
                "question_type": "likert",
                "options": scale["labels"],
                "required": True,
                "min_value": scale["min_value"],
                "max_value": scale["max_value"],
                "help_text": None,
            },
            index,
        )

    return (
        {
            "id": f"Q{question_number}",
            "text": prompt,
            "question_type": "multi_choice" if multi_choice else "single_choice",
            "options": options,
            "required": True,
            "min_value": None,
            "max_value": None,
            "help_text": None,
        },
        index,
    )


def _parse_open_text_block(
    *,
    lines: Sequence[str],
    start_index: int,
    question_number: int,
    current_concept: Optional[str],
) -> tuple[Optional[Dict[str, Any]], int]:
    index = start_index + 1
    prompt_lines: List[str] = []

    while index < len(lines):
        line = lines[index]
        if _is_control_line(line) or line.lower().startswith("order details"):
            break
        prompt_lines.append(line)
        index += 1

    if not prompt_lines:
        return None, index

    return (
        {
            "id": f"Q{question_number}",
            "text": _compose_question_text(prompt_lines, current_concept),
            "question_type": "open_text",
            "options": [],
            "required": True,
            "min_value": None,
            "max_value": None,
            "help_text": None,
        },
        index,
    )


def _parse_matrix_block(
    *,
    lines: Sequence[str],
    start_index: int,
    question_number: int,
    parse_warnings: List[str],
) -> tuple[List[Dict[str, Any]], int]:
    index = start_index + 1
    prompt_lines: List[str] = []

    while index < len(lines):
        line = lines[index]
        if _is_control_line(line) or _is_subquestions_header(line) or _is_answer_options_header(line):
            break
        prompt_lines.append(line)
        index += 1

    if index >= len(lines) or not _is_subquestions_header(lines[index]):
        return [], index

    prompt = _clean_text(" ".join(prompt_lines))
    index += 1

    row_lines: List[str] = []
    while index < len(lines):
        line = lines[index]
        if _is_control_line(line) or _is_answer_options_header(line):
            break
        row_lines.append(_clean_text(line))
        index += 1

    if index >= len(lines) or not _is_answer_options_header(lines[index]):
        return [], index

    index += 1
    option_lines: List[str] = []
    while index < len(lines):
        line = lines[index]
        if _is_control_line(line) or line.lower().startswith("order details"):
            break
        option_lines.append(_clean_option(line))
        index += 1

    scale = _extract_numeric_scale(option_lines)
    if scale is None:
        return [], index

    questions: List[Dict[str, Any]] = []
    for row_index, row_label in enumerate(row_lines, start=1):
        questions.append(
            {
                "id": f"Q{question_number}_{row_index}",
                "text": f"{prompt} — {row_label}",
                "question_type": "likert",
                "options": scale["labels"],
                "required": True,
                "min_value": scale["min_value"],
                "max_value": scale["max_value"],
                "help_text": None,
            }
        )

    parse_warnings.append(
        f"Expanded matrix question Q{question_number} into {len(row_lines)} sub-questions "
        f"(Q{question_number}_1 .. Q{question_number}_{len(row_lines)})."
    )
    return questions, index


def _extract_concept_label(lines: Sequence[str], start_index: int) -> Optional[str]:
    index = start_index
    while index < len(lines):
        line = lines[index]
        if _is_control_line(line):
            return None
        cleaned = _clean_text(line)
        if cleaned.lower().startswith("concept "):
            return re.sub(r"\s*\[.*$", "", cleaned).strip()
        if cleaned.lower() in {"please read:", "instruction text"}:
            index += 1
            continue
        return None
    return None


def _compose_question_text(prompt_lines: Sequence[str], current_concept: Optional[str]) -> str:
    prompt = _clean_text(" ".join(prompt_lines))
    if current_concept and prompt in _GENERIC_CONCEPT_PROMPTS:
        return f"{current_concept} — {prompt}"
    return prompt


def _extract_numeric_scale(options: Sequence[str]) -> Optional[Dict[str, Any]]:
    if not options:
        return None

    values: List[int] = []
    labels: List[str] = []
    for option in options:
        explicit = re.match(r"^(?P<value>\d+)\s*-\s*(?P<label>.+)$", option)
        if explicit:
            values.append(int(explicit.group("value")))
            labels.append(_clean_text(explicit.group("label")))
            continue

        implicit = re.match(r"^(?P<value>\d+)$", option)
        if implicit:
            numeric_value = int(implicit.group("value"))
            values.append(numeric_value)
            labels.append(str(numeric_value))
            continue

        return None

    expected = list(range(1, len(values) + 1))
    if values != expected:
        return None

    return {
        "min_value": values[0],
        "max_value": values[-1],
        "labels": labels,
    }


def _is_control_line(line: str) -> bool:
    return bool(_CONTROL_LINE_RE.match(line))


def _is_answer_options_header(line: str) -> bool:
    return line.strip().lower().startswith("answer options")


def _is_subquestions_header(line: str) -> bool:
    return line.strip().lower().startswith("sub-questions")


def _clean_text(value: str) -> str:
    cleaned = _TRAILING_TAG_RE.sub("", value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _clean_option(value: str) -> str:
    cleaned = _TRAILING_TAG_RE.sub("", value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
