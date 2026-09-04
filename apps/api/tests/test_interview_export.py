from __future__ import annotations

import csv
import io

import pytest

from src.services.interview_export import build_interview_transcript_export


def _create_study(client) -> str:
    response = client.post("/api/v1/studies", json={})
    assert response.status_code == 200
    return response.json()["data"]["study"]["study_id"]


def _transcript_payload() -> dict:
    return {
        "persona_id": "P/007 home",
        "interviewee_model": "provider/model-mini",
        "turns": [
            {"role": "student", "text": 'What matters, and why?\nPlease say "why".'},
            {"role": "persona", "text": "A quiet office, mostly.\n\nIt would help me focus."},
        ],
    }


def test_interview_transcript_exports_rfc_compatible_csv(client):
    study_id = _create_study(client)

    response = client.post(
        f"/api/v1/studies/{study_id}/interview/export?format=csv",
        json=_transcript_payload(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        'attachment; filename="interview-P-007-home.csv"'
    )
    assert response.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows == [
        {
            "turn": "1",
            "role": "student",
            "speaker": "Student",
            "text": 'What matters, and why?\nPlease say "why".',
            "persona_id": "P/007 home",
            "interviewee_model": "provider/model-mini",
        },
        {
            "turn": "2",
            "role": "persona",
            "speaker": "P/007 home",
            "text": "A quiet office, mostly.\n\nIt would help me focus.",
            "persona_id": "P/007 home",
            "interviewee_model": "provider/model-mini",
        },
    ]


def test_interview_transcript_csv_neutralizes_spreadsheet_formulas(client):
    study_id = _create_study(client)
    payload = {
        "persona_id": "=persona",
        "interviewee_model": "@model",
        "turns": [
            {"role": "student", "text": "+1+1"},
            {"role": "persona", "text": "-2+3"},
            {"role": "student", "text": " \t=4+4"},
        ],
    }

    response = client.post(
        f"/api/v1/studies/{study_id}/interview/export?format=csv",
        json=payload,
    )

    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows == [
        {
            "turn": "1",
            "role": "student",
            "speaker": "Student",
            "text": "'+1+1",
            "persona_id": "'=persona",
            "interviewee_model": "'@model",
        },
        {
            "turn": "2",
            "role": "persona",
            "speaker": "'=persona",
            "text": "'-2+3",
            "persona_id": "'=persona",
            "interviewee_model": "'@model",
        },
        {
            "turn": "3",
            "role": "student",
            "speaker": "Student",
            "text": "' \t=4+4",
            "persona_id": "'=persona",
            "interviewee_model": "'@model",
        },
    ]


def test_interview_transcript_exports_readable_markdown(client):
    study_id = _create_study(client)

    response = client.post(
        f"/api/v1/studies/{study_id}/interview/export?format=markdown",
        json=_transcript_payload(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        'attachment; filename="interview-P-007-home.md"'
    )
    assert response.text == """# Interview transcript

- Persona: `P/007 home`
- Interviewee model: `provider/model-mini`

## Transcript

### 1. Student

> What matters, and why?
> Please say "why".

### 2. P/007 home

> A quiet office, mostly.
>
> It would help me focus.
"""


def test_interview_transcript_export_rejects_empty_turns_and_unknown_formats(client):
    study_id = _create_study(client)
    payload = _transcript_payload()
    payload["turns"] = []

    empty_response = client.post(
        f"/api/v1/studies/{study_id}/interview/export?format=csv",
        json=payload,
    )
    unknown_response = client.post(
        f"/api/v1/studies/{study_id}/interview/export?format=pdf",
        json=_transcript_payload(),
    )

    assert empty_response.status_code == 400
    assert empty_response.json()["error"]["code"] == "validation_error"
    assert unknown_response.status_code == 400
    assert unknown_response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    ("persona_id", "expected_filename"),
    [
        ("../", "interview-transcript.csv"),
        ("P" * 80, f"interview-{'P' * 64}.csv"),
    ],
)
def test_interview_transcript_export_generates_safe_bounded_filenames(
    persona_id, expected_filename
):
    payload = _transcript_payload()
    payload["persona_id"] = persona_id

    export = build_interview_transcript_export(payload, "csv")

    assert export.filename == expected_filename
