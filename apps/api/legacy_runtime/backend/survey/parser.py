"""Survey parsing utilities for markdown, DOCX, and PDF uploads."""

from __future__ import annotations

import io
import importlib
import re
from typing import Any, Dict, List, Optional


QUESTION_PATTERNS = [
	re.compile(r"^\s*(?P<id>[A-Za-z]?\d+[A-Za-z]?)\s*[:\.\-]\s*(?P<text>.+)$", re.IGNORECASE),
	re.compile(r"^\s*Question\s*(?P<id>[A-Za-z]?\d+[A-Za-z]?)\s*[:\.\-]\s*(?P<text>.+)$", re.IGNORECASE),
]

# Only accept these keys from `Key: value` metadata lines.
_KNOWN_METADATA_KEYS = {"type", "options", "range", "help", "required"}

# Patterns that signal multi-select in question text.
_MULTI_SELECT_PATTERNS = [
	re.compile(r"select\s+up\s+to\s+\d+", re.IGNORECASE),
	re.compile(r"select\s+all\s+that\s+apply", re.IGNORECASE),
	re.compile(r"choose\s+up\s+to\s+\d+", re.IGNORECASE),
	re.compile(r"check\s+all\s+that\s+apply", re.IGNORECASE),
]


def parse_uploaded_survey(file_name: str, file_bytes: bytes) -> Dict[str, Any]:
	"""Parse an uploaded survey file into a raw normalized payload.

	Supported formats:
	- .md (preferred)
	- .docx
	- .pdf (best-effort)
	"""
	extension = file_name.lower().rsplit(".", maxsplit=1)[-1]

	if extension == "md":
		text = file_bytes.decode("utf-8", errors="ignore")
		payload = parse_text_to_raw_payload(text=text, source_format="md")
		if not payload["questions"]:
			raise ValueError(
				"No recognizable questions were found in the Markdown file. "
				"Expected lines like `Q1:` and `Type:`."
			)
		return payload

	if extension == "docx":
		text = _extract_text_from_docx(file_bytes)
		payload = parse_text_to_raw_payload(text=text, source_format="docx")
		if not payload["questions"]:
			payload["parse_warnings"].append(
				"DOCX parsing found little usable question structure. Consider Markdown format for best results."
			)
		return payload

	if extension == "pdf":
		text = _extract_text_from_pdf(file_bytes)
		payload = parse_text_to_raw_payload(text=text, source_format="pdf")
		payload["parse_warnings"].append(
			"PDF parsing is best-effort and may require manual review. Markdown is recommended."
		)
		if len(text.strip()) < 30:
			payload["parse_warnings"].append("Very little text could be extracted from the PDF.")
		return payload

	raise ValueError("Unsupported file type. Please upload .md, .docx, or .pdf.")


def parse_text_to_raw_payload(text: str, source_format: str) -> Dict[str, Any]:
	"""Parse survey-like text into a raw payload used by schema normalizer.

	Expected markdown pattern (simple rule-based format):
	- Question line: `Q1: ...` or `Question 1: ...`
	- Optional metadata lines under a question: `Type:`, `Options:`, `Range:`
	- Markdown checkbox options: `- [ ] Option text`
	- Markdown table scales: header row with labels + row with `| 1 | 2 | ... |`
	- Matrix tables: `| Row item | o | o | o | ... |`
	"""
	lines = [line.rstrip() for line in text.splitlines()]
	non_empty_lines = [line.strip() for line in lines if line.strip()]

	survey_title: Optional[str] = None
	description_lines: List[str] = []
	parse_warnings: List[str] = []

	# Prefer markdown headings for title if present.
	for line in non_empty_lines:
		if line.startswith("#"):
			survey_title = line.lstrip("#").strip()
			break
	if survey_title is None and non_empty_lines:
		survey_title = non_empty_lines[0]

	questions: List[Dict[str, Any]] = []
	current_question: Optional[Dict[str, Any]] = None
	# Track pending label row from markdown tables for Likert scale context.
	pending_table_labels: Optional[List[str]] = None
	# Track matrix rows (barrier-style tables).
	pending_matrix_rows: List[Dict[str, Any]] = []

	for raw_line in lines:
		line = raw_line.strip()
		if not line:
			continue

		# Detect the start of a new question block and finalize the previous one.
		question_start = _match_question_start(line)
		if question_start is not None:
			if current_question is not None:
				# Before appending, expand any pending matrix rows.
				_flush_matrix_rows(current_question, pending_matrix_rows, questions, parse_warnings)
				pending_matrix_rows = []
				pending_table_labels = None
			question_id, question_text = question_start
			current_question = {
				"id": question_id,
				"text": question_text,
				"question_type": None,
				"options": [],
				"required": True,
				"min_value": None,
				"max_value": None,
				"help_text": None,
			}
			continue

		# Capture description text before first question.
		if current_question is None:
			if not line.startswith("#"):
				description_lines.append(line)
			continue

		# --- Try known metadata key:value lines (Bug 4 fix: restrict to known keys) ---
		key_value = _parse_key_value_line(line)
		if key_value is not None:
			key, value = key_value
			if key == "type":
				current_question["question_type"] = value.lower()
			elif key == "options":
				options_text = value
				if "|" in options_text:
					options = [part.strip() for part in options_text.split("|")]
				else:
					options = [part.strip() for part in options_text.split(",")]
				current_question["options"] = [opt for opt in options if opt]
			elif key == "range":
				range_text = value
				range_match = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", range_text)
				if range_match:
					current_question["min_value"] = int(range_match.group(1))
					current_question["max_value"] = int(range_match.group(2))
				else:
					parse_warnings.append(f"Could not parse range for {current_question['id']}: '{range_text}'")
			elif key == "help":
				current_question["help_text"] = value
			elif key == "required":
				current_question["required"] = value.lower() not in {"no", "false", "0"}
			continue

		# --- Try markdown checkbox options ---
		checkbox_option = _parse_markdown_checkbox_option(line)
		if checkbox_option is not None:
			if checkbox_option not in current_question["options"]:
				current_question["options"].append(checkbox_option)
			continue

		# --- Try markdown table lines (numeric scale, label row, matrix row) ---
		if "|" in line:
			# Check for separator row (|---|---|...) — skip it.
			if _is_table_separator(line):
				continue

			# Check for matrix row (| item text | o | o | o | ... |).
			matrix_row = _parse_matrix_row(line)
			if matrix_row is not None:
				pending_matrix_rows.append(matrix_row)
				continue

			# Check for numeric scale row (| 1 | 2 | 3 | 4 | 5 |).
			numeric_scale = _parse_markdown_table_numeric_scale(line)
			if numeric_scale is not None:
				min_value, max_value = numeric_scale
				current_question["min_value"] = min_value
				current_question["max_value"] = max_value
				# If we have pending labels, attach them now.
				if pending_table_labels and not current_question["options"]:
					current_question["options"] = pending_table_labels
				pending_table_labels = None
				continue

			# Check for label row (| Not at all interested | Slightly interested | ... |).
			labels = _parse_table_label_row(line)
			if labels is not None:
				pending_table_labels = labels
				continue

		# Skip other lines (blockquotes, headings, prose, etc.).
		continue

	# Flush any remaining question + matrix rows.
	if current_question is not None:
		_flush_matrix_rows(current_question, pending_matrix_rows, questions, parse_warnings)

	# --- Type inference pass ---
	for question in questions:
		if question["question_type"]:
			continue

		# Check for Likert from text-embedded scale pattern (e.g., "(1 = ... 5 = ...)").
		likert_scale = _infer_likert_scale_from_text(question.get("text"))
		if likert_scale is not None:
			question["question_type"] = "likert"
			question["min_value"] = likert_scale[0]
			question["max_value"] = likert_scale[1]
			parse_warnings.append(
				f"Inferred likert for {question['id']} from question text scale pattern."
			)
			continue

		if question["options"] and question["min_value"] is not None and question["max_value"] is not None:
			# Options + numeric range = Likert with labels.
			question["question_type"] = "likert"
			parse_warnings.append(f"Inferred likert for {question['id']} because range and scale labels were provided.")
		elif question["options"]:
			# Check for multi-select signals in question text (Bug 3 fix).
			if _is_multi_select(question.get("text", "")):
				question["question_type"] = "multi_choice"
				parse_warnings.append(f"Inferred multi_choice for {question['id']} because text indicates multiple selections.")
			else:
				question["question_type"] = "single_choice"
				parse_warnings.append(f"Inferred single_choice for {question['id']} because options were provided.")
		elif question["min_value"] is not None and question["max_value"] is not None:
			question["question_type"] = "likert"
			parse_warnings.append(f"Inferred likert for {question['id']} because range was provided.")
		else:
			question["question_type"] = "open_text"
			parse_warnings.append(f"Inferred open_text for {question['id']} because type was missing.")

	description = "\n".join(description_lines).strip() or None

	return {
		"survey_title": survey_title,
		"description": description,
		"source_format": source_format,
		"parse_warnings": parse_warnings,
		"questions": questions,
	}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flush_matrix_rows(
	parent_question: Dict[str, Any],
	matrix_rows: List[Dict[str, Any]],
	questions: List[Dict[str, Any]],
	parse_warnings: List[str],
) -> None:
	"""Expand matrix rows into individual sub-questions, or append parent as-is."""
	if not matrix_rows:
		questions.append(parent_question)
		return

	# Determine the scale from the matrix rows (all should have the same column count).
	num_cols = matrix_rows[0]["num_columns"]
	min_value = 1
	max_value = num_cols

	# If the parent question already has min/max from a numeric scale row, use those.
	if parent_question["min_value"] is not None and parent_question["max_value"] is not None:
		min_value = parent_question["min_value"]
		max_value = parent_question["max_value"]

	parent_id = parent_question["id"]
	parent_text = parent_question["text"]

	for idx, row in enumerate(matrix_rows, start=1):
		sub_id = f"{parent_id}_{idx}"
		sub_text = f"{parent_text} — {row['item_label']}"
		sub_question = {
			"id": sub_id,
			"text": sub_text,
			"question_type": "likert",
			"options": parent_question.get("options", [])[:],
			"required": parent_question.get("required", True),
			"min_value": min_value,
			"max_value": max_value,
			"help_text": parent_question.get("help_text"),
		}
		questions.append(sub_question)

	parse_warnings.append(
		f"Expanded matrix question {parent_id} into {len(matrix_rows)} sub-questions ({parent_id}_1 .. {parent_id}_{len(matrix_rows)})."
	)


def _match_question_start(line: str) -> Optional[tuple[str, str]]:
	"""Match a question start line and return normalized (id, text)."""
	# Normalize common markdown wrappers used in provided survey docs.
	candidate = line.strip()
	candidate = re.sub(r"^\*\*(.+)\*\*$", r"\1", candidate).strip()
	candidate = candidate.replace("**", "")

	for pattern in QUESTION_PATTERNS:
		match = pattern.match(candidate)
		if match:
			raw_id = match.group("id").strip()
			if raw_id and raw_id[0].isalpha():
				normalized_id = raw_id.upper()
			else:
				normalized_id = f"Q{raw_id}"
			return normalized_id, match.group("text").strip()
	return None


def _parse_key_value_line(line: str) -> Optional[tuple[str, str]]:
	"""Parse metadata lines like `Type: ...` — restricted to known keys only."""
	match = re.match(r"^\s*([A-Za-z_ ]+)\s*:\s*(.+?)\s*$", line)
	if not match:
		return None
	key = match.group(1).strip().lower().replace(" ", "_")
	# Bug 4 fix: only accept known metadata keys to avoid false positives.
	if key not in _KNOWN_METADATA_KEYS:
		return None
	value = match.group(2).strip()
	return key, value


def _parse_markdown_checkbox_option(line: str) -> Optional[str]:
	"""Extract answer option text from markdown checkbox lines like '- [ ] Option'."""
	match = re.match(r"^\s*[-*]\s*\[\s*\]\s*(.+?)\s*$", line)
	if not match:
		return None
	option = match.group(1).strip()
	option = re.sub(r"\s*→.*$", "", option).strip()
	option = option.rstrip(".")
	return option or None


def _is_table_separator(line: str) -> bool:
	"""Detect markdown table separator rows like |---|---|---|."""
	parts = [part.strip() for part in line.strip().strip("|").split("|")]
	return all(re.fullmatch(r"-{1,}|:?-+:?", part or "") for part in parts) and len(parts) >= 2


def _parse_markdown_table_numeric_scale(line: str) -> Optional[tuple[int, int]]:
	"""Extract min/max scale from markdown table rows like '| 1 | 2 | 3 | 4 | 5 |'."""
	if "|" not in line:
		return None
	parts = [part.strip() for part in line.strip().strip("|").split("|")]
	if len(parts) < 2:
		return None
	if any(not re.fullmatch(r"\d+", part or "") for part in parts):
		return None
	numbers = [int(part) for part in parts]
	if len(numbers) < 2:
		return None
	return min(numbers), max(numbers)


def _parse_table_label_row(line: str) -> Optional[List[str]]:
	"""Extract scale labels from table header rows like '| Not at all | Slightly | ... |'.

	Returns a list of label strings, or None if it doesn't look like a label row.
	Filters out rows that are purely separator rows or numeric rows.
	"""
	if "|" not in line:
		return None
	parts = [part.strip() for part in line.strip().strip("|").split("|")]
	if len(parts) < 2:
		return None
	# Skip if all parts are numeric (that's a scale row, not a label row).
	if all(re.fullmatch(r"\d+", part or "") for part in parts if part):
		return None
	# Skip if it looks like a separator row.
	if all(re.fullmatch(r"-{1,}|:?-+:?", part or "") for part in parts):
		return None
	# Skip if all cells are single-char placeholders like "o" (matrix data row).
	if all(re.fullmatch(r"[oOxX•·\-]", part or "") for part in parts if part):
		return None
	# Filter out empty parts.
	labels = [part for part in parts if part]
	if len(labels) < 2:
		return None
	# Heuristic: label rows should have cells with at least some alphabetic text.
	alpha_count = sum(1 for label in labels if any(c.isalpha() for c in label))
	if alpha_count < 2:
		return None
	return labels


def _parse_matrix_row(line: str) -> Optional[Dict[str, Any]]:
	"""Detect matrix data rows like '| The total cost (~$23,000) | o | o | o | o | o |'.

	A matrix row has a first cell with descriptive text, followed by cells that are
	single-character placeholders (o, x, •, etc.) used as radio-position markers.
	"""
	if "|" not in line:
		return None
	parts = [part.strip() for part in line.strip().strip("|").split("|")]
	if len(parts) < 3:
		return None
	# First cell should be descriptive text (not a single char, not empty, not a number).
	first_cell = parts[0]
	if not first_cell or len(first_cell) < 2:
		return None
	if re.fullmatch(r"\d+", first_cell):
		return None
	# Remaining cells should be single-char placeholders.
	data_cells = parts[1:]
	if len(data_cells) < 2:
		return None
	placeholder_count = sum(
		1 for cell in data_cells
		if re.fullmatch(r"[oOxX•·\-]", cell or "")
	)
	# At least 80% of data cells should be placeholders.
	if placeholder_count / len(data_cells) < 0.8:
		return None

	return {
		"item_label": first_cell,
		"num_columns": len(data_cells),
	}


def _is_multi_select(text: str) -> bool:
	"""Check if question text signals a multi-select question."""
	if not text:
		return False
	for pattern in _MULTI_SELECT_PATTERNS:
		if pattern.search(text):
			return True
	return False


def _infer_likert_scale_from_text(text: object) -> Optional[tuple[int, int]]:
	"""Infer simple numeric scale from question text (e.g., '1 = ... 5 = ...')."""
	if text is None:
		return None
	text_value = str(text)
	match = re.search(r"\(\s*(\d+)\s*=.*?(\d+)\s*=.*?\)", text_value)
	if not match:
		return None
	min_value = int(match.group(1))
	max_value = int(match.group(2))
	if min_value >= max_value:
		return None
	return min_value, max_value


def _extract_text_from_docx(file_bytes: bytes) -> str:
	"""Extract text from DOCX paragraphs and simple table cells."""
	try:
		docx_module = importlib.import_module("docx")
	except ModuleNotFoundError as error:
		raise ImportError("python-docx is required for .docx survey parsing.") from error

	doc = docx_module.Document(io.BytesIO(file_bytes))

	lines: List[str] = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
	for table in doc.tables:
		for row in table.rows:
			for cell in row.cells:
				cell_text = cell.text.strip()
				if cell_text:
					lines.append(cell_text)

	return "\n".join(lines)


def _extract_text_from_pdf(file_bytes: bytes) -> str:
	"""Extract text from PDF pages using pypdf (no OCR)."""
	try:
		pypdf_module = importlib.import_module("pypdf")
	except ModuleNotFoundError as error:
		raise ImportError("pypdf is required for .pdf survey parsing.") from error

	reader = pypdf_module.PdfReader(io.BytesIO(file_bytes))
	page_texts: List[str] = []
	for page in reader.pages:
		extracted = page.extract_text() or ""
		if extracted.strip():
			page_texts.append(extracted)
	return "\n".join(page_texts)
