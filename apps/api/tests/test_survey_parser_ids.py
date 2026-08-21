"""F-14: the survey parser must accept meaningful question ids, not only Q-numbers.

`QUESTION_PATTERNS` required an id of the form `[A-Za-z]?\\d+[A-Za-z]?` — an optional letter, digits,
an optional letter. `Q1`, `S3`, `Q0B` matched; `BENEFIT`, `PRICE`, `CONCERN` could never match, so a
survey using semantic ids was rejected outright with "No recognizable questions were found".

That forced every custom study into `Q1..Qn` naming, which the insights layer then interprets as Neo's
price-point interest, purchase likelihood and primary intended use — making the Neo semantic collision
unavoidable rather than merely possible.

The first group of tests characterises the Neo preset so widening the pattern cannot silently break the
32-question demo. The rest drive the new behaviour.
"""

from __future__ import annotations

import pathlib
from pathlib import Path

import pytest

import importlib.util


# The legacy engine exists in two copies (see QA baseline §4): the nested `NeoSmart-Hackathon-App`
# repo, which local dev and `conftest`'s LEGACY_APP_ROOT point at, and `apps/api/legacy_runtime`,
# which the Dockerfile copies into the image. Only the latter is version-controlled by this repo and
# actually ships, so that is the copy these tests exercise. Loading it by path also avoids colliding
# with any `backend.*` module already imported from the other root.
_VENDORED_PARSER = (
    pathlib.Path(__file__).resolve().parents[1]
    / "legacy_runtime"
    / "backend"
    / "survey"
    / "parser.py"
)


@pytest.fixture()
def parser():
    spec = importlib.util.spec_from_file_location("vendored_survey_parser", _VENDORED_PARSER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _parse_md(parser, text: str):
    return parser.parse_text_to_raw_payload(text=text, source_format="md")


# --------------------------------------------------------------------------------------
# Characterisation: lock in current Neo behaviour before widening the pattern.
# --------------------------------------------------------------------------------------

def _neo_preset_text(test_settings) -> str:
    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "legacy_runtime"
        / "Provided Info"
        / "Neo Smart Living — Survey_HighPriority.md"
    )
    return path.read_text(encoding="utf-8")


def test_neo_preset_still_parses_its_full_question_set(parser, test_settings):
    payload = _parse_md(parser, _neo_preset_text(test_settings))
    ids = [q["id"] for q in payload["questions"]]

    assert len(ids) == 32
    # screener, category baseline, the core ladder, and the expanded barrier matrix
    for expected in ("S3", "Q0B", "Q1", "Q2", "Q3", "Q5_1", "Q5_7"):
        assert expected in ids, f"{expected} disappeared from the Neo preset"


def test_neo_preset_keeps_its_question_types(parser, test_settings):
    payload = _parse_md(parser, _neo_preset_text(test_settings))
    types = {}
    for q in payload["questions"]:
        types[q["question_type"]] = types.get(q["question_type"], 0) + 1
    assert types.get("single_choice") == 8
    assert types.get("likert") == 24


# --------------------------------------------------------------------------------------
# New behaviour: semantic ids must parse.
# --------------------------------------------------------------------------------------

SEMANTIC_SURVEY = """# StudyFlow FocusPlan Study

**BENEFIT. Main benefit** Which benefit would matter most to you?

- [ ] Automatic study scheduling
- [ ] Deadline reminders

**INTEREST. Interest level** How interested are you in a study-planning subscription?

| Not at all interested | Slightly interested | Moderately interested | Very interested | Extremely interested |
| --- | --- | --- | --- | --- |
| 1 | 2 | 3 | 4 | 5 |

**CONCERN. Main concern** What would stop you from subscribing?
"""


def test_semantic_question_ids_are_accepted(parser):
    payload = _parse_md(parser, SEMANTIC_SURVEY)
    ids = [q["id"] for q in payload["questions"]]
    assert ids == ["BENEFIT", "INTEREST", "CONCERN"]


def test_semantic_ids_still_resolve_question_types(parser):
    payload = _parse_md(parser, SEMANTIC_SURVEY)
    by_id = {q["id"]: q for q in payload["questions"]}
    assert by_id["BENEFIT"]["question_type"] == "single_choice"
    assert len(by_id["BENEFIT"]["options"]) == 2
    assert by_id["INTEREST"]["question_type"] == "likert"
    assert by_id["INTEREST"]["min_value"] == 1
    assert by_id["INTEREST"]["max_value"] == 5


# --------------------------------------------------------------------------------------
# Guard: widening the pattern must not turn prose into questions.
# --------------------------------------------------------------------------------------

PROSE_SURVEY = """# Sample study

Mode: Online self-administered survey
Note: answer honestly

**Q1. Interest** How interested are you?

Note: this note sits inside a question block
Type: likert
Range: 1-5
"""


def test_prose_key_value_lines_do_not_become_questions(parser):
    payload = _parse_md(parser, PROSE_SURVEY)
    ids = [q["id"] for q in payload["questions"]]

    assert ids == ["Q1"], f"prose lines leaked in as questions: {ids}"
    assert payload["questions"][0]["question_type"] == "likert"
