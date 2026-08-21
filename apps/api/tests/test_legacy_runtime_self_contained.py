"""F-01: the legacy engine must resolve from inside this repository.

`NeoSmart-Hackathon-App` was a gitlink (mode 160000) pointing at a repository owned by a different
GitHub account, with no `.gitmodules`. A fresh clone produced an empty directory there, so
`LEGACY_APP_ROOT` pointed at nothing, every `load_module("backend.*")` failed and the whole backend
suite died at import. `git submodule update --init` could not help — there was no mapping to read.

`apps/api/legacy_runtime` is now the canonical runtime for local development and production alike, so
there is one copy rather than two that can silently drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.services.study_service import NEO_SURVEY_PRESET_FILENAME

# Every module the API loads through `load_module(..., settings.legacy_app_root)`.
RUNTIME_MODULES = [
    "backend/analysis/benchmark.py",
    "backend/analysis/findings.py",
    "backend/analysis/realism.py",
    "backend/analysis/stability.py",
    "backend/grounding/geography_context.py",
    "backend/grounding/prior_sampler.py",
    "backend/presets.py",
    "backend/schemas.py",
    "backend/scraper.py",
    "backend/simulation/llm_client.py",
    "backend/simulation/persona_generator.py",
    "backend/simulation/prompt_builder.py",
    "backend/simulation/run_manager.py",
    "backend/survey/parser.py",
    "backend/survey/schema_normalizer.py",
    "backend/survey/validator.py",
    "backend/vision.py",
]

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_configured_legacy_root_is_tracked_inside_this_repository(test_settings):
    root = Path(test_settings.legacy_app_root).resolve()

    assert root.is_dir(), f"legacy root does not exist: {root}"
    assert REPO_ROOT in root.parents, (
        f"legacy root {root} is outside this repository, so a fresh clone cannot populate it"
    )
    assert root.name == "legacy_runtime", (
        f"expected the vendored runtime to be canonical, got {root.name!r}"
    )


@pytest.mark.parametrize("relative_path", RUNTIME_MODULES)
def test_every_runtime_module_is_present(test_settings, relative_path):
    root = Path(test_settings.legacy_app_root)
    assert (root / relative_path).is_file(), f"missing runtime module: {relative_path}"


def test_neo_survey_preset_resolves_from_the_legacy_root(test_settings):
    """`backend/presets.py` resolves the preset as `<legacy root>/Provided Info/<file>`."""
    root = Path(test_settings.legacy_app_root)
    assert (root / "Provided Info" / NEO_SURVEY_PRESET_FILENAME).is_file()


def test_docx_parser_fixture_is_vendored(test_settings):
    """test_upload_aytm_docx_succeeds_with_fallback_parser reads this from the legacy root."""
    root = Path(test_settings.legacy_app_root)
    matches = list((root / "Provided Info").glob("aytm Survey*.docx"))
    assert matches, "the AYTM DOCX fixture must ship with the runtime or its test cannot pass in CI"


def test_grounding_prior_build_scripts_are_preserved(test_settings):
    """The ACS/AHS/CEX pipeline is the only way to ever build the grounding priors."""
    root = Path(test_settings.legacy_app_root)
    scripts = root / "scripts"
    assert scripts.is_dir(), "prior-building scripts must not be lost with the gitlink"
    for expected in ("build_grounding_priors.py", "download_acs_pums.sh"):
        assert (scripts / expected).is_file(), f"missing {expected}"
