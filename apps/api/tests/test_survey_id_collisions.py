"""F-08: an unnamed question must not steal an id the document already uses.

`normalize_survey_payload` gave any question that declares no id the name `Q{index}`, without checking
whether the survey already had a question called that. A Google Forms PDF export begins with an
unlabelled "Email*" field, which became `Q1` -- and the survey's own `Q1. Purchase interest at $23,000`
was still called `Q1`. The validator then rejected the whole upload:

    HTTP 400  Duplicate question ids found: Q1

The file is valid. Exporting a Google Form to PDF is the most likely classroom path, and it could not
be uploaded at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters.legacy_backend.runtime import load_module


@pytest.fixture
def normalizer(test_settings):
    return load_module("backend.survey.schema_normalizer", test_settings.legacy_app_root)


def _raw(questions: list[dict]) -> dict:
    return {"survey_title": "Upload", "source_format": "pdf", "parse_warnings": [], "questions": questions}


def test_an_unnamed_question_does_not_take_an_id_the_survey_declares(normalizer):
    """The Google Forms shape: an unlabelled field first, a declared Q1 after it."""
    schema = normalizer.normalize_survey_payload(
        _raw(
            [
                {"text": "Email*", "question_type": "open_text"},
                {"id": "Q1", "text": "Purchase interest at $23,000", "question_type": "open_text"},
            ]
        )
    )

    ids = [question.id for question in schema.questions]
    assert len(ids) == len(set(ids)), f"the upload still collides: {ids}"
    assert "Q1" in ids, "the question that declared Q1 keeps it"
    assert ids[0] != "Q1", "the unnamed question must not claim a declared id"


def test_the_declared_question_keeps_its_own_id_and_meaning(normalizer):
    """Renaming the wrong one would silently move the researcher's question."""
    schema = normalizer.normalize_survey_payload(
        _raw(
            [
                {"text": "Email*", "question_type": "open_text"},
                {"id": "Q1", "text": "Purchase interest at $23,000", "question_type": "open_text"},
            ]
        )
    )
    by_id = {question.id: question.text for question in schema.questions}

    assert by_id["Q1"] == "Purchase interest at $23,000"


def test_the_researcher_is_told_a_question_was_renamed(normalizer):
    schema = normalizer.normalize_survey_payload(
        _raw(
            [
                {"text": "Email*", "question_type": "open_text"},
                {"id": "Q1", "text": "Purchase interest at $23,000", "question_type": "open_text"},
            ]
        )
    )

    assert any("Email*" in warning or "already used" in warning for warning in schema.parse_warnings), (
        f"a silent rename is worse than the error it replaces: {schema.parse_warnings}"
    )


def test_a_survey_that_names_nothing_is_numbered_exactly_as_before(normalizer):
    """No collision, no change: plain uploads keep the familiar Q1..Qn numbering."""
    schema = normalizer.normalize_survey_payload(
        _raw([{"text": f"Question {index}"} for index in range(1, 5)])
    )

    assert [question.id for question in schema.questions] == ["Q1", "Q2", "Q3", "Q4"]


def test_several_unnamed_questions_around_declared_ids_stay_unique(normalizer):
    schema = normalizer.normalize_survey_payload(
        _raw(
            [
                {"text": "Email*"},
                {"text": "Name*"},
                {"id": "Q1", "text": "Declared one"},
                {"id": "Q2", "text": "Declared two"},
                {"text": "Anything else?"},
            ]
        )
    )

    ids = [question.id for question in schema.questions]
    assert len(ids) == len(set(ids)), ids
    assert {"Q1", "Q2"} <= set(ids)


def test_the_google_forms_export_now_parses(test_settings):
    """End to end on the real file, when this checkout has it.

    The source PDFs are reference material and are deliberately not vendored into the runtime, so this
    skips rather than fails where they are absent.
    """
    pdf = (
        Path(test_settings.legacy_app_root).parents[2]
        / "NeoSmart-Hackathon-App"
        / "Provided Info"
        / "Neo Smart Living — Tahoe Mini Survey (High + Medium Priority) - Google Forms.pdf"
    )
    if not pdf.exists():
        pytest.skip(f"source PDF not present in this checkout: {pdf}")

    pypdf = pytest.importorskip("pypdf")
    parser = load_module("backend.survey.parser", test_settings.legacy_app_root)
    normalizer = load_module("backend.survey.schema_normalizer", test_settings.legacy_app_root)
    validator = load_module("backend.survey.validator", test_settings.legacy_app_root)

    text = "\n".join((page.extract_text() or "") for page in pypdf.PdfReader(str(pdf)).pages)
    schema = normalizer.normalize_survey_payload(parser.parse_text_to_raw_payload(text, "pdf"))

    validator.validate_survey_schema(schema)  # previously raised "Duplicate question ids found: Q1"
    assert len(schema.questions) > 20
