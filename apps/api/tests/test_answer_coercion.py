"""Regression tests for live-answer coercion.

Models echo survey options with cosmetic variation (trailing punctuation,
enumeration prefixes, quotes). Rejecting those answers silently routes the
question onto the deterministic mock-answer fallback, which is what made real
runs look "grounded" while quietly serving demo data.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters.legacy_backend.runtime import load_module


API_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = API_ROOT / "legacy_runtime"

INTEREST_OPTIONS = [
    "Not at all interested",
    "Slightly interested",
    "Moderately interested",
    "Very interested",
    "Extremely interested",
]


@pytest.fixture(scope="module")
def run_manager():
    return load_module("backend.simulation.run_manager", LEGACY_ROOT)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Moderately interested", "Moderately interested"),
        ("Moderately interested.", "Moderately interested"),
        ("moderately interested", "Moderately interested"),
        ("  Very interested  ", "Very interested"),
        ('"Very interested"', "Very interested"),
        ("C) Moderately interested", "Moderately interested"),
        ("3. Very interested", "Very interested"),
        ("Moderately  interested", "Moderately interested"),
        ("Extremely interested!", "Extremely interested"),
    ],
)
def test_single_choice_accepts_cosmetic_variation(run_manager, raw, expected):
    assert run_manager._match_survey_option(raw, INTEREST_OPTIONS) == expected


@pytest.mark.parametrize("raw", ["", "banana", "interested", "somewhat curious"])
def test_single_choice_rejects_unmatchable_or_ambiguous(run_manager, raw):
    """Ambiguous text must fall back rather than silently pick a wrong option."""
    assert run_manager._match_survey_option(raw, INTEREST_OPTIONS) is None


def test_multi_choice_normalizes_and_dedupes(run_manager):
    schemas = load_module("backend.schemas", LEGACY_ROOT)
    question = schemas.SurveyQuestion(
        id="Q1",
        text="Which apply?",
        question_type="multi_choice",
        options=["Cost", "Space", "Permits"],
    )
    coerced = run_manager._coerce_openrouter_answer_value(question, ["cost.", "Space", "Cost"])
    assert coerced == ["Cost", "Space"]


def test_single_choice_question_coerces_trailing_period(run_manager):
    schemas = load_module("backend.schemas", LEGACY_ROOT)
    question = schemas.SurveyQuestion(
        id="Q30",
        text="How interested are you?",
        question_type="single_choice",
        options=INTEREST_OPTIONS,
    )
    assert (
        run_manager._coerce_openrouter_answer_value(question, "Moderately interested.")
        == "Moderately interested"
    )


@pytest.mark.parametrize(
    "header,expected",
    [
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff\xe0", "image/jpeg"),
    ],
)
def test_supported_image_formats_are_detected(header, expected):
    from src.adapters.legacy_backend.domain import detect_product_image_mime

    assert detect_product_image_mime(header + b"\x00" * 32) == expected


@pytest.mark.parametrize(
    "header,expected_label",
    [
        (b"\x00\x00\x00\x18ftypheic", "HEIC/HEIF"),
        (b"RIFF\x00\x00\x00\x00WEBP", "WEBP"),
        (b"GIF89a", "GIF"),
        (b"%PDF-1.7", "PDF"),
    ],
)
def test_unsupported_image_formats_are_named_not_sent_to_the_provider(header, expected_label):
    """A renamed HEIC used to surface as an opaque provider HTTP 400."""
    from src.adapters.legacy_backend.domain import detect_product_image_mime
    from src.services.exceptions import ValidationApiError

    with pytest.raises(ValidationApiError) as excinfo:
        detect_product_image_mime(header + b"\x00" * 32)
    assert expected_label in excinfo.value.message


def test_non_image_bytes_are_rejected():
    from src.adapters.legacy_backend.domain import detect_product_image_mime
    from src.services.exceptions import ValidationApiError

    with pytest.raises(ValidationApiError):
        detect_product_image_mime(b"this is definitely not an image file")
