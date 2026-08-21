"""F-08: PDF survey support, and refusing documents that are not surveys.

`pypdf` returns a Google Forms export in a layout that hides its structure from a line-by-line reader.
Per page it emits, in this order:

    1. one numbered block per question -- "7." then a control line ("Mark only one oval.",
       "Check all that apply.", "Mark only one oval per row.") then the option labels
    2. the question headings for those same items -- "Q5b. Other barrier (optional)" plus wrapped body
    3. a page footer: the export timestamp and the docs.google.com URL

So a question and its options are always separated, usually by other questions' options and by page
furniture. Read top to bottom they look like unrelated prose, which is why every question came out as
`open_text` and the upload produced no charts.

The recoverable fact is positional: **the i-th numbered block on a page belongs to the i-th question
heading on that page.** That holds across all 22 content pages of the reference export, including the
pages where a question has no options at all.

The second half of this file is the other side of F-08: four of the five PDFs in this project are not
surveys -- a design brief, a 60-page results report, a marketing brochure, and a slide deck -- and each
was accepted as one, with questions invented from prose.
"""

from __future__ import annotations

import collections
from pathlib import Path

import pytest

from src.adapters.legacy_backend.domain import parse_normalize_validate_survey
from src.services.exceptions import ValidationApiError

PROVIDED = "Provided Info"


def _legacy_provided(test_settings) -> Path:
    return Path(test_settings.legacy_app_root) / PROVIDED


def _source_provided(test_settings) -> Path:
    """The un-vendored reference PDFs, which are reference material rather than runtime files."""
    return Path(test_settings.legacy_app_root).parents[2] / "NeoSmart-Hackathon-App" / PROVIDED


def _parse(test_settings, path: Path) -> dict:
    return parse_normalize_validate_survey(path.name, path.read_bytes(), Path(test_settings.legacy_app_root))


def _require(path: Path):
    if not path.exists():
        pytest.skip(f"reference document not present in this checkout: {path.name}")


# --------------------------------------------------------------------------------------------------
# PDF Test A - the real Google Forms survey export
# --------------------------------------------------------------------------------------------------

GOOGLE_FORMS = "Neo Smart Living — Tahoe Mini Survey (High + Medium Priority) - Google Forms.pdf"


@pytest.fixture
def google_forms_schema(test_settings):
    path = _source_provided(test_settings) / GOOGLE_FORMS
    _require(path)
    return _parse(test_settings, path)


def test_google_forms_export_uploads_and_has_unique_ids(google_forms_schema):
    questions = google_forms_schema["questions"]
    ids = [q["id"] for q in questions]

    assert len(questions) >= 20, f"a 25-page survey export yielded {len(questions)} questions"
    assert len(ids) == len(set(ids)), (
        f"duplicate ids: {[i for i, c in collections.Counter(ids).items() if c > 1]}"
    )


def test_google_forms_export_is_not_flattened_to_open_text(google_forms_schema):
    """The failure this test exists for: 43 questions, every one of them open text, no charts."""
    questions = google_forms_schema["questions"]
    typed = [q for q in questions if q["question_type"] != "open_text"]

    assert len(typed) >= 15, (
        f"only {len(typed)} of {len(questions)} questions recovered a type; the export declares "
        "'Mark only one oval' on most of them"
    )


def test_google_forms_options_stay_with_their_own_question(google_forms_schema):
    """Positional pairing is the whole reconstruction, so a drift by one must fail loudly."""
    by_id = {q["id"]: q for q in google_forms_schema["questions"]}

    q6 = by_id.get("Q6")
    assert q6 is not None, f"Q6 missing; ids were {sorted(by_id)[:20]}"
    assert q6["question_type"] == "single_choice"
    joined = " | ".join(q6["options"])
    assert "The total cost" in joined and "HOA restrictions" in joined, (
        f"Q6 'Single greatest barrier' did not receive the barrier list: {q6['options']}"
    )

    q26 = by_id.get("Q26")
    assert q26 is not None
    assert any("IE MTB Club" in option for option in q26["options"]), (
        f"Q26 received the wrong block's options: {q26['options']}"
    )


def test_google_forms_linear_scales_become_likert_with_their_bounds(google_forms_schema):
    """'Not at all interested / 1 2 3 4 5 / Extremely interested' is a scale, not free text."""
    by_id = {q["id"]: q for q in google_forms_schema["questions"]}
    q0b = by_id.get("Q0B") or by_id.get("Q0b")

    assert q0b is not None, f"Q0b missing; ids were {sorted(by_id)[:20]}"
    assert q0b["question_type"] == "likert"
    assert q0b["min_value"] == 1 and q0b["max_value"] == 5


def test_google_forms_questions_without_options_stay_open_text(google_forms_schema):
    """Q5b is genuinely free text in the source. Inventing options for it would be worse than none."""
    by_id = {q["id"]: q for q in google_forms_schema["questions"]}
    q5b = by_id.get("Q5B") or by_id.get("Q5b")

    assert q5b is not None
    assert q5b["question_type"] == "open_text"
    assert not q5b["options"]


def test_google_forms_page_furniture_never_becomes_a_question(google_forms_schema):
    """Every page carries a timestamp line and a docs.google.com URL."""
    for question in google_forms_schema["questions"]:
        text = str(question["text"])
        assert "docs.google.com" not in text, f"page footer parsed as a question: {text[:70]}"
        assert "11:43 AM" not in text, f"page header parsed as a question: {text[:70]}"
        for option in question["options"]:
            assert "docs.google.com" not in str(option)


def test_unrecoverable_matrix_rows_are_reported_rather_than_invented(google_forms_schema):
    """Q5's seven barrier rows are word-wrapped and duplicated by pypdf beyond safe reassembly.

    The 1-5 scale is genuinely present, so the question is kept as a scale -- but the reader has to be
    told the per-row items were lost, because a silently single-row barrier matrix is a wrong survey.
    """
    warnings = " ".join(google_forms_schema.get("parse_warnings") or [])
    assert "matrix" in warnings.lower(), (
        f"the matrix limitation was not reported: {google_forms_schema.get('parse_warnings')}"
    )


# --------------------------------------------------------------------------------------------------
# PDF Test B - a second, differently-worded export, to prove nothing is keyed to the reference file
# --------------------------------------------------------------------------------------------------

SECOND_EXPORT = """Widget Co Customer Study
1.
Mark only one oval.
Daily
Weekly
Rarely
2.
Check all that apply.
Price
Durability
Design
3.
Mark only one oval.
Very dissatisfied
1 2 3 4 5
Very satisfied
4.
W1. Usage frequency
How often do you use the widget?
*
W2. Purchase drivers
Which of these influenced your purchase?
*
W3. Overall satisfaction
How satisfied are you overall?
*
W4. Anything else
Tell us anything else you would like us to know.
7/1/26, 09:00 AM Widget Co Customer Study
https://docs.google.com/forms/d/ABCDEF/edit 2/2
"""


def test_a_different_google_forms_export_reconstructs_too(test_settings, tmp_path):
    """Same layout, entirely different content: the reconstruction must be about shape, not this survey."""
    from src.adapters.legacy_backend.runtime import load_module

    normalizer = load_module("backend.survey.schema_normalizer", test_settings.legacy_app_root)
    parser = load_module("backend.survey.parser", test_settings.legacy_app_root)

    schema = normalizer.normalize_survey_payload(
        parser.parse_text_to_raw_payload(SECOND_EXPORT, "pdf")
    )
    by_id = {q.id: q for q in schema.questions}

    assert set(by_id) == {"W1", "W2", "W3", "W4"}, f"got {sorted(by_id)}"
    assert by_id["W1"].question_type == "single_choice"
    assert by_id["W1"].options == ["Daily", "Weekly", "Rarely"]
    assert by_id["W2"].question_type == "multi_choice"
    assert by_id["W3"].question_type == "likert"
    assert (by_id["W3"].min_value, by_id["W3"].max_value) == (1, 5)
    assert by_id["W4"].question_type == "open_text"


# --------------------------------------------------------------------------------------------------
# PDF Test C - documents that are not surveys
# --------------------------------------------------------------------------------------------------

NOT_SURVEYS = [
    ("Neo Smart Living Background.pdf", "a marketing brochure"),
    ("Aytm_x_Neo_Smart_Living_Joint_Challenge.docx.pdf", "a design brief"),
    ("survey-760085-2026-03-25-summary.pdf", "a 60-page results report"),
    ("Aytm_x_Neo_Smart_Living_Challenge_Intro.pptx.pdf", "a slide deck"),
]


@pytest.mark.parametrize("file_name,description", NOT_SURVEYS)
def test_a_document_that_is_not_a_survey_is_refused(test_settings, file_name, description):
    path = _source_provided(test_settings) / file_name
    _require(path)

    with pytest.raises(ValidationApiError) as excinfo:
        _parse(test_settings, path)

    message = str(excinfo.value)
    assert "does not appear to contain a recognizable survey" in message, (
        f"{description} was refused, but not for the right reason: {message}"
    )


# --------------------------------------------------------------------------------------------------
# Regression D/E/F - what must not move
# --------------------------------------------------------------------------------------------------


def test_neo_markdown_schema_is_unchanged(test_settings):
    """Regression D. The Neo preset is the demo everything else is measured against."""
    path = _legacy_provided(test_settings) / "Neo Smart Living — Survey_HighPriority.md"
    _require(path)
    schema = _parse(test_settings, path)
    types = collections.Counter(q["question_type"] for q in schema["questions"])
    ids = [q["id"] for q in schema["questions"]]

    assert len(schema["questions"]) == 32, f"expected 32 questions, got {len(schema['questions'])}"
    assert types["likert"] == 24 and types["single_choice"] == 8, dict(types)
    assert [i for i in ids if i.startswith("Q5_")] == [f"Q5_{n}" for n in range(1, 8)], (
        "the Q5 barrier matrix must still expand to seven rows"
    )


def test_aytm_docx_keeps_the_richer_typed_schema(test_settings):
    """Regression E. The primary parser returns 32 all-open-text for this file; the fallback returns 39 typed."""
    path = _legacy_provided(test_settings) / "aytm Survey #760085  (Neo Smart Living — Tahoe Mini Survey).docx"
    _require(path)
    schema = _parse(test_settings, path)
    types = collections.Counter(q["question_type"] for q in schema["questions"])

    assert len(schema["questions"]) == 39, f"expected the fallback's 39 questions, got {len(schema['questions'])}"
    assert types["likert"] == 26 and types["single_choice"] == 9, dict(types)


def test_cortado_markdown_custom_survey_is_unchanged(test_settings):
    """Regression F. A non-Neo survey with semantic content must keep parsing as it did."""
    path = _legacy_provided(test_settings) / "Cortado Roasters — Coffee Subscription Survey.md"
    _require(path)
    schema = _parse(test_settings, path)
    typed = [q for q in schema["questions"] if q["question_type"] != "open_text"]

    assert len(schema["questions"]) == 32
    assert len(typed) == 32, "every Cortado question is typed today"


def test_lost_ligatures_are_reported_not_silently_swallowed(google_forms_schema):
    """pypdf drops ffi/fl/fi entirely, so "office" arrives as "oce".

    Which ligature was lost is not recoverable. Guessing would put invented words in front of
    respondents, so the loss is reported and the NULs left behind are stripped -- Postgres rejects
    them outright, so leaving them in would fail the run later and further from the cause.
    """
    warnings = " ".join(google_forms_schema.get("parse_warnings") or [])
    assert "ligature" in warnings.lower(), f"ligature loss unreported: {google_forms_schema.get('parse_warnings')}"

    for question in google_forms_schema["questions"]:
        assert "\x00" not in str(question["text"])
        for option in question["options"]:
            assert "\x00" not in str(option)
