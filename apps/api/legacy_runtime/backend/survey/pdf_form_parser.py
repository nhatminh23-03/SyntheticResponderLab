"""Reconstruct a survey from the text `pypdf` returns for a Google Forms PDF export.

Read line by line, such an export looks like prose: every question comes out as open text and the
upload produces no charts. The structure is there, but it is positional rather than sequential.

Per page, `pypdf` emits three groups in this order:

    1. one numbered block per question -- ``7.`` then a control line ("Mark only one oval.",
       "Check all that apply.", "Mark only one oval per row.") then the option labels
    2. the question headings for those same items -- ``Q5b. Other barrier (optional)`` and their
       wrapped body text
    3. page furniture -- the export timestamp and the ``docs.google.com`` URL

So a question is never adjacent to its own options. What is reliable is that **the i-th numbered block
on a page belongs to the i-th question heading on that page** -- verified across all 22 content pages of
the reference export, including pages where one question has no options at all.

This reads shape, not content. Nothing here refers to any particular survey.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# A page ends at the Forms footer. The timestamp line above it belongs to the same furniture.
_FOOTER = re.compile(r"^https?://docs\.google\.com/forms/", re.I)
_TIMESTAMP = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},\s+\d{1,2}:\d{2}\s*[AP]M\b", re.I)

_NUMBERED = re.compile(r"^\s*(\d{1,3})\.\s*$")
_SECTION = re.compile(r"^\s*Section\s+[A-Z0-9]+\s*:", re.I)
_REQUIRED_NOTE = re.compile(r"^\s*\*\s*(Indicates required question)?\s*$", re.I)
_SCALE = re.compile(r"^\s*\d+(?:\s+\d+)+\s*$")

# A survey identifier: one or two letters, then digits, optionally a lowercase part letter. This is
# deliberately narrow -- the export's prose contains lines like "Dr. Lin said..." and "out. The next",
# which a looser rule reads as question headings.
_HEADING = re.compile(r"^\s*(?P<id>[A-Za-z]{1,2}\d{1,3}[a-z]?)\.\s+(?P<title>\S.*)$")

_CONTROLS = {
    "mark only one oval per row": "matrix",
    "mark only one oval": "single_choice",
    "check all that apply": "multi_choice",
}

# Google Forms appends its branching instructions to the option label itself, and names the destination
# section in parentheses. Forms then renders that destination's title as the next line, so the title is
# both furniture and a reliable marker for where a block's options stop.
_SKIP_LOGIC = re.compile(r"\s+Skip to (question|section)\b.*$", re.I)
_SKIP_TARGET = re.compile(r"\s+Skip to section\s+\d+\s*\((?P<title>[^)]+)\)", re.I)

# Extraction drops some ligatures entirely, leaving NULs behind. They are unusable as text and Postgres
# rejects them outright, so they are removed and the loss is reported rather than papered over.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

MIN_RECONSTRUCTED_QUESTIONS = 3


def _control_kind(line: str) -> Optional[str]:
    stripped = line.strip().rstrip(".").lower()
    for phrase, kind in _CONTROLS.items():
        if stripped.startswith(phrase):
            return kind
    return None


def _split_pages(lines: List[str]) -> List[List[str]]:
    pages: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        if _FOOTER.match(line.strip()):
            pages.append(current)
            current = []
            continue
        if _TIMESTAMP.match(line.strip()):
            continue
        current.append(line)
    if current:
        pages.append(current)
    return pages


def _clean_option(line: str) -> str:
    text = _SKIP_LOGIC.sub("", _CONTROL_CHARS.sub("", line).strip()).strip()
    if text.endswith(":"):
        text = text[:-1].strip()
    return text


def _scrub(text: str) -> str:
    return _CONTROL_CHARS.sub("", text)


def _is_noise(line: str) -> bool:
    stripped = line.strip()
    return (
        not stripped
        or _SECTION.match(stripped) is not None
        or _REQUIRED_NOTE.match(stripped) is not None
        or _control_kind(stripped) is not None
    )


def _page_headings(page: List[str]) -> List[Dict[str, Any]]:
    """Question headings on a page, each with the body text that follows it."""
    headings: List[Dict[str, Any]] = []
    for index, line in enumerate(page):
        match = _HEADING.match(line)
        if not match:
            continue
        body: List[str] = []
        for follow in page[index + 1:]:
            stripped = follow.strip()
            if not stripped or _HEADING.match(follow) or _NUMBERED.match(follow) or _is_noise(follow):
                break
            if _SCALE.match(follow):
                break
            body.append(stripped)
        headings.append(
            {
                "id": match.group("id").upper(),
                "title": match.group("title").strip(),
                "body": " ".join(body).strip(),
                "line": index,
            }
        )
    return headings


def _page_blocks(page: List[str], heading_lines: set) -> List[Dict[str, Any]]:
    """Numbered answer blocks on a page, with their control kind, options and scale."""
    starts = [index for index, line in enumerate(page) if _NUMBERED.match(line)]
    blocks: List[Dict[str, Any]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(page)
        kind: Optional[str] = None
        options: List[str] = []
        scale: Optional[tuple] = None
        skip_targets: set = set()
        started = False
        for index in range(start + 1, end):
            line = page[index]
            control = _control_kind(line)
            if control:
                kind = kind or control
                started = True
                continue
            if _SCALE.match(line):
                numbers = [int(value) for value in line.split()]
                scale = (numbers[0], numbers[-1])
                started = True
                continue
            if not started:
                # A matrix block carries its heading before the scale; skip until a control appears.
                continue
            # Options run contiguously from the control line. Anything else -- a section title, the
            # required-question note, another question's heading or body, or the destination title of a
            # skip rule -- means the list has ended. Continuing past it swept page prose into the
            # answer options.
            if (
                index in heading_lines
                or _HEADING.match(line)
                or _NUMBERED.match(line)
                or _is_noise(line)
                or line.strip() in skip_targets
            ):
                break
            target = _SKIP_TARGET.search(line)
            if target:
                skip_targets.add(target.group("title").strip())
            options.append(line)
        blocks.append({"kind": kind, "options": options, "scale": scale})
    return blocks


def _body_line_numbers(page: List[str], headings: List[Dict[str, Any]]) -> set:
    """Line indices belonging to a heading or its wrapped body, so options never absorb them."""
    owned = set()
    for heading in headings:
        owned.add(heading["line"])
        for index in range(heading["line"] + 1, len(page)):
            line = page[index]
            stripped = line.strip()
            if not stripped or _HEADING.match(line) or _NUMBERED.match(line) or _is_noise(line):
                break
            if _SCALE.match(line):
                break
            owned.add(index)
    return owned


def _build_question(heading: Dict[str, Any], block: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
    text = _scrub(" ".join(part for part in (heading["title"], heading["body"]) if part).strip())
    kind = block["kind"]
    options = [_clean_option(option) for option in block["options"]]
    options = [option for option in options if option]

    question: Dict[str, Any] = {
        "id": heading["id"],
        "text": text or heading["title"],
        "question_type": "open_text",
        "options": [],
        "required": True,
        "min_value": None,
        "max_value": None,
        "help_text": None,
    }

    if kind == "matrix":
        low, high = block["scale"] or (1, 5)
        question.update({"question_type": "likert", "min_value": low, "max_value": high})
        warnings.append(
            f"{heading['id']} is a matrix question. Its per-row items could not be recovered from the "
            f"PDF -- the export wraps and repeats them -- so it was kept as a single {low}-{high} scale. "
            "Upload the .md or .docx original to get one question per row."
        )
        return question

    if block["scale"]:
        low, high = block["scale"]
        question.update({"question_type": "likert", "min_value": low, "max_value": high})
        if options:
            question["help_text"] = " to ".join(options[:2])
        return question

    if kind in ("single_choice", "multi_choice") and options:
        question.update({"question_type": kind, "options": options})
        return question

    if kind in ("single_choice", "multi_choice") and not options:
        warnings.append(
            f"{heading['id']} declares choices in the PDF but none could be read, so it was kept as "
            "open text rather than given invented options."
        )
    return question


def reconstruct_google_forms_export(text: str) -> Optional[Dict[str, Any]]:
    """Rebuild a survey from a Google Forms PDF export, or return ``None`` if it is not one.

    Returning ``None`` rather than a poor guess is deliberate: the caller then keeps whatever the
    general parser produced, and a document that is not a form is never dressed up as one.
    """
    lines = text.splitlines()
    if not any(_control_kind(line) for line in lines):
        return None

    questions: List[Dict[str, Any]] = []
    warnings: List[str] = []
    dropped_blocks = 0

    for page in _split_pages(lines):
        headings = _page_headings(page)
        if not headings:
            continue
        blocks = _page_blocks(page, _body_line_numbers(page, headings))
        if not blocks:
            continue
        if len(blocks) != len(headings):
            # Pairing is positional, so an unequal page cannot be resolved safely. Take the questions
            # that can be paired from the start and record what was left rather than guessing.
            dropped_blocks += abs(len(blocks) - len(headings))
        for heading, block in zip(headings, blocks):
            questions.append(_build_question(heading, block, warnings))

    if len(questions) < MIN_RECONSTRUCTED_QUESTIONS:
        return None

    if dropped_blocks:
        warnings.append(
            f"{dropped_blocks} answer block(s) could not be matched to a question heading and were "
            "skipped. Check the parsed questions against the original document."
        )

    if _CONTROL_CHARS.search(text):
        # Extraction dropped typographic ligatures outright, so words such as "office" arrive as "oce".
        # Which ligature was lost is not recoverable, and guessing would put invented words in front of
        # respondents, so the gap is reported instead.
        warnings.append(
            "Some characters were lost when the PDF was read — typographic ligatures (ffi, fl, fi) do "
            "not survive extraction, so a few words may be missing letters. Check the question and "
            "option text, or upload the .md or .docx original."
        )

    warnings.insert(
        0,
        "Rebuilt from a Google Forms PDF export by pairing each page's answer blocks with that page's "
        "question headings. Verify the questions against the original before running a study.",
    )
    return {
        "survey_title": None,
        "description": None,
        "source_format": "pdf",
        "parse_warnings": warnings,
        "questions": questions,
    }
