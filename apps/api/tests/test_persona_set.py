"""Fixed persona set: 15 grounded candidates, a reviewer selects exactly 5, interviews reuse them.

The selection pins exact PersonaPreviewPersona rows (by UUID) and their candidate batch (preview
run), so later interview runs use those five records even after newer previews repoint
Study.latest_persona_preview_run_id. Candidate generation must stay on the grounded-priors path
and must never read the withheld research materials (AYTM dataset/report, Tony transcript).
"""

from __future__ import annotations

import re
import sys
import uuid

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_persona(index: int, id_prefix: str = "PERS") -> dict:
    return {
        "persona_id": f"{id_prefix}_{index:03d}",
        "age_bucket": "35-44",
        "income_bucket": "middle",
        "household_size_bucket": "3-4",
        "ownership": "own",
        "home_type": "single_family",
        "work_mode": "remote",
        "lifestyle_tags": ["remote work", "home improvement"],
        "likely_use_case": "backyard office",
        "likely_barrier": "permit uncertainty",
        "segment_label": "Backyard office homeowners",
        "affordability_pressure": "medium",
        "housing_burden_proxy": "unknown",
        "spend_intensity_bucket": "medium",
        "fit_tier": "strong",
        "awareness_stage": "aware",
    }


def _stub_preview(monkeypatch, id_prefix: str = "PERS", mode: str = "grounded_priors"):
    def _preview(**kwargs):
        count = kwargs["sample_size"]
        return {
            "generation_mode": mode,
            "grounded_priors_available": True,
            "cex_affordability_available": False,
            "prior_notes": [{"prior_table_name": "age_income_priors", "source_variant": "global"}],
            "personas": [_fake_persona(i + 1, id_prefix) for i in range(count)],
        }

    monkeypatch.setattr("src.services.study_service.preview_personas", _preview)


def _study_ready_for_preview(client, study_mode: str = "general", sample_size: int = 80) -> str:
    """The smallest setup the preview endpoint accepts: saved audience + saved experiment."""
    created = client.post("/api/v1/studies", json={"study_mode": study_mode}).json()["data"]["study"]
    study_id = created["study_id"]

    audience = client.patch(
        f"/api/v1/studies/{study_id}/audience",
        json={"age_min": 30, "age_max": 60, "homeowner_only": True},
    )
    assert audience.status_code == 200, audience.text

    experiment = client.patch(
        f"/api/v1/studies/{study_id}/experiment",
        json={
            "sample_size": sample_size,
            "selected_models": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            "experiment_mode": "mirror",
            "reruns_per_persona": 1,
        },
    )
    assert experiment.status_code == 200, experiment.text
    return study_id


def _generate_candidates(client, study_id: str, count: int = 15) -> dict:
    response = client.post(
        f"/api/v1/studies/{study_id}/personas/preview",
        json={"sample_size": count},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["persona_preview"]


def _candidate_ids(preview_payload: dict) -> list:
    return [persona["candidate_id"] for persona in preview_payload["personas"]]


def _patch_selection(client, study_id: str, preview_run_id: str, selections: list):
    return client.patch(
        f"/api/v1/studies/{study_id}/persona-set",
        json={"preview_run_id": preview_run_id, "selections": selections},
    )


# ---------------------------------------------------------------------------
# Requirements 1-3: 15 candidates, persisted, grounded, with stable ids
# ---------------------------------------------------------------------------


def test_fifteen_grounded_candidates_with_stable_ids(client):
    """The real pipeline generates and persists exactly 15 grounded candidates, each addressable."""
    created = client.post("/api/v1/studies", json={"study_mode": "neo_smart"}).json()["data"]["study"]
    study_id = created["study_id"]
    bootstrap = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/preset/neo")
    assert bootstrap.status_code == 200, bootstrap.text

    preview = _generate_candidates(client, study_id, count=15)

    assert preview["generation_mode"] == "grounded_priors"
    assert preview["request"]["sample_size"] == 15
    assert len(preview["personas"]) == 15
    for row_index, persona in enumerate(preview["personas"]):
        assert persona["row_index"] == row_index
        uuid.UUID(persona["candidate_id"])  # raises if not a real UUID
    assert len(set(_candidate_ids(preview))) == 15


# ---------------------------------------------------------------------------
# Requirement: draft selection round-trip (edit before finalization)
# ---------------------------------------------------------------------------


def test_selection_draft_roundtrip(client, monkeypatch):
    _stub_preview(monkeypatch)
    study_id = _study_ready_for_preview(client)
    preview = _generate_candidates(client, study_id)
    candidates = _candidate_ids(preview)

    empty = client.get(f"/api/v1/studies/{study_id}/persona-set")
    assert empty.status_code == 200, empty.text
    assert empty.json()["data"]["persona_set"] is None

    first = _patch_selection(
        client,
        study_id,
        preview["preview_id"],
        [
            {"candidate_id": candidates[0], "reviewer_note": "strong anchor persona"},
            {"candidate_id": candidates[1]},
            {"candidate_id": candidates[2]},
        ],
    )
    assert first.status_code == 200, first.text
    persona_set = first.json()["data"]["persona_set"]
    assert persona_set["status"] == "draft"
    assert persona_set["set_id"].startswith("fps_")
    assert persona_set["preview_run_id"] == preview["preview_id"]
    assert persona_set["generation_mode"] == "grounded_priors"
    assert persona_set["candidate_count"] == 15
    assert len(persona_set["candidates"]) == 15
    assert [s["candidate_id"] for s in persona_set["selections"]] == candidates[:3]
    assert persona_set["selections"][0]["reviewer_note"] == "strong anchor persona"

    replaced = _patch_selection(
        client,
        study_id,
        preview["preview_id"],
        [{"candidate_id": cid} for cid in candidates[5:10]],
    )
    assert replaced.status_code == 200, replaced.text
    persona_set = replaced.json()["data"]["persona_set"]
    assert [s["candidate_id"] for s in persona_set["selections"]] == candidates[5:10]

    reloaded = client.get(f"/api/v1/studies/{study_id}/persona-set")
    assert reloaded.status_code == 200
    persona_set = reloaded.json()["data"]["persona_set"]
    assert [s["candidate_id"] for s in persona_set["selections"]] == candidates[5:10]
    assert persona_set["status"] == "draft"


# ---------------------------------------------------------------------------
# Requirement 4: fewer or more than 5 cannot finalize
# ---------------------------------------------------------------------------


def test_finalize_requires_exactly_five(client, monkeypatch):
    _stub_preview(monkeypatch)
    study_id = _study_ready_for_preview(client)
    preview = _generate_candidates(client, study_id)
    candidates = _candidate_ids(preview)

    no_draft = client.post(f"/api/v1/studies/{study_id}/persona-set/finalize")
    assert no_draft.status_code == 409

    _patch_selection(client, study_id, preview["preview_id"], [{"candidate_id": c} for c in candidates[:4]])
    four = client.post(f"/api/v1/studies/{study_id}/persona-set/finalize")
    assert four.status_code == 409
    assert "5" in four.json()["error"]["message"]

    _patch_selection(client, study_id, preview["preview_id"], [{"candidate_id": c} for c in candidates[:6]])
    six = client.post(f"/api/v1/studies/{study_id}/persona-set/finalize")
    assert six.status_code == 409

    _patch_selection(client, study_id, preview["preview_id"], [{"candidate_id": c} for c in candidates[:5]])
    five = client.post(f"/api/v1/studies/{study_id}/persona-set/finalize")
    assert five.status_code == 200, five.text
    persona_set = five.json()["data"]["persona_set"]
    assert persona_set["status"] == "finalized"
    assert persona_set["finalized_at"] is not None

    after_finalize = _patch_selection(
        client, study_id, preview["preview_id"], [{"candidate_id": c} for c in candidates[5:10]]
    )
    assert after_finalize.status_code == 409

    again = client.post(f"/api/v1/studies/{study_id}/persona-set/finalize")
    assert again.status_code == 409


# ---------------------------------------------------------------------------
# Selection integrity: only candidates of the pinned run, no duplicates
# ---------------------------------------------------------------------------


def test_selection_rejects_foreign_unknown_and_duplicate_candidates(client, monkeypatch):
    _stub_preview(monkeypatch)
    study_id = _study_ready_for_preview(client)
    run_a = _generate_candidates(client, study_id)
    run_a_candidates = _candidate_ids(run_a)

    _stub_preview(monkeypatch, id_prefix="NEWER")
    run_b = _generate_candidates(client, study_id)

    unknown = _patch_selection(
        client, study_id, run_a["preview_id"], [{"candidate_id": str(uuid.uuid4())}]
    )
    assert unknown.status_code in (400, 404, 422)

    foreign = _patch_selection(
        client, study_id, run_b["preview_id"], [{"candidate_id": run_a_candidates[0]}]
    )
    assert foreign.status_code in (400, 404, 422)

    duplicate = _patch_selection(
        client,
        study_id,
        run_a["preview_id"],
        [{"candidate_id": run_a_candidates[0]}, {"candidate_id": run_a_candidates[0]}],
    )
    assert duplicate.status_code in (400, 422)

    bogus_run = _patch_selection(
        client, study_id, "ppr_does_not_exist", [{"candidate_id": run_a_candidates[0]}]
    )
    assert bogus_run.status_code in (400, 404, 422)


# ---------------------------------------------------------------------------
# Requirements 5-6: exactly 5 persisted, reload returns the same five
# ---------------------------------------------------------------------------


def test_reload_returns_the_same_five_personas(client, monkeypatch):
    _stub_preview(monkeypatch)
    study_id = _study_ready_for_preview(client)
    preview = _generate_candidates(client, study_id)
    candidates = _candidate_ids(preview)
    chosen = [candidates[1], candidates[3], candidates[6], candidates[9], candidates[12]]

    _patch_selection(
        client,
        study_id,
        preview["preview_id"],
        [{"candidate_id": cid, "reviewer_note": f"pick {i}"} for i, cid in enumerate(chosen)],
    )
    finalized = client.post(f"/api/v1/studies/{study_id}/persona-set/finalize")
    assert finalized.status_code == 200, finalized.text

    reloaded = client.get(f"/api/v1/studies/{study_id}/persona-set")
    persona_set = reloaded.json()["data"]["persona_set"]
    assert persona_set["status"] == "finalized"
    assert sorted(s["candidate_id"] for s in persona_set["selections"]) == sorted(chosen)
    notes = {s["candidate_id"]: s["reviewer_note"] for s in persona_set["selections"]}
    assert notes[chosen[0]] == "pick 0"

    by_candidate_id = {c["candidate_id"]: c for c in persona_set["candidates"]}
    selected_profiles = [by_candidate_id[cid] for cid in chosen]
    assert [p["persona_id"] for p in selected_profiles] == [
        "PERS_002",
        "PERS_004",
        "PERS_007",
        "PERS_010",
        "PERS_013",
    ]
    for profile in selected_profiles:
        assert profile["awareness_stage"] == "aware"
        assert profile["likely_use_case"] == "backyard office"


# ---------------------------------------------------------------------------
# Requirement 7: interviews use the exact finalized set, never a newer preview
# ---------------------------------------------------------------------------


def _stub_interview_batch(monkeypatch, captured: dict):
    def _batch(**kwargs):
        captured["personas"] = kwargs["personas"]
        return [
            {"persona_id": p["persona_id"], "persona": p, "answers": []}
            for p in kwargs["personas"]
        ]

    monkeypatch.setattr("src.services.interview_service._run_interview_batch", _batch)
    monkeypatch.setattr(
        "src.services.interview_service.score_interview_batch",
        lambda **kwargs: {"summary": "stubbed"},
    )


def test_interview_uses_finalized_set_not_latest_preview(client, monkeypatch):
    _stub_preview(monkeypatch)
    study_id = _study_ready_for_preview(client)
    run_a = _generate_candidates(client, study_id)
    candidates = _candidate_ids(run_a)
    chosen = candidates[:5]

    _patch_selection(client, study_id, run_a["preview_id"], [{"candidate_id": c} for c in chosen])
    finalized = client.post(f"/api/v1/studies/{study_id}/persona-set/finalize")
    assert finalized.status_code == 200, finalized.text

    # A newer preview repoints Study.latest_persona_preview_run_id — the set must not drift.
    _stub_preview(monkeypatch, id_prefix="NEWER")
    _generate_candidates(client, study_id)

    client.app.state.settings.openrouter_api_key = "test-openrouter-key"
    captured: dict = {}
    _stub_interview_batch(monkeypatch, captured)

    response = client.post(f"/api/v1/studies/{study_id}/interview/runs", json={})
    assert response.status_code == 200, response.text
    payload = response.json()["data"]["interview_run"]

    assert payload["persona_count"] == 5
    assert [pair["persona_id"] for pair in payload["pairs"]] == [
        "PERS_001",
        "PERS_002",
        "PERS_003",
        "PERS_004",
        "PERS_005",
    ]
    assert payload["persona_set_id"].startswith("fps_")
    assert payload["preview_run_id"] == run_a["preview_id"]
    assert len(captured["personas"]) == 5
    assert all(p["persona_id"].startswith("PERS_") for p in captured["personas"])


def test_interview_without_set_still_uses_latest_preview(client, monkeypatch):
    _stub_preview(monkeypatch)
    study_id = _study_ready_for_preview(client)
    preview = _generate_candidates(client, study_id)

    client.app.state.settings.openrouter_api_key = "test-openrouter-key"
    captured: dict = {}
    _stub_interview_batch(monkeypatch, captured)

    response = client.post(f"/api/v1/studies/{study_id}/interview/runs", json={})
    assert response.status_code == 200, response.text
    payload = response.json()["data"]["interview_run"]

    assert payload["persona_count"] == 15
    assert payload["persona_set_id"] is None
    assert payload["preview_run_id"] == preview["preview_id"]


# ---------------------------------------------------------------------------
# Candidate count and Experiment sample_size stay separate concepts
# ---------------------------------------------------------------------------


def test_candidate_generation_leaves_experiment_sample_size_alone(client, monkeypatch):
    _stub_preview(monkeypatch)
    study_id = _study_ready_for_preview(client, sample_size=80)
    preview = _generate_candidates(client, study_id, count=15)
    assert preview["request"]["sample_size"] == 15

    study = client.get(f"/api/v1/studies/{study_id}").json()["data"]["study"]
    assert study["experiment"]["value"]["sample_size"] == 80


# ---------------------------------------------------------------------------
# Requirement 8: the withheld research materials are never read
# ---------------------------------------------------------------------------

_EXCLUDED_PATH_PATTERN = re.compile(r"aytm|tony|760085|provided info|benchmark", re.IGNORECASE)
_audit_state = {"armed": False, "hits": []}
_audit_hook_installed = False


def _install_audit_hook():
    # Audit hooks are process-permanent, so install one flag-gated hook at most.
    global _audit_hook_installed
    if _audit_hook_installed:
        return

    def _hook(event, args):
        if not _audit_state["armed"] or event != "open":
            return
        try:
            path = str(args[0]) if args else ""
        except Exception:
            return
        if _EXCLUDED_PATH_PATTERN.search(path):
            _audit_state["hits"].append(path)

    sys.addaudithook(_hook)
    _audit_hook_installed = True


def test_candidate_generation_never_opens_withheld_research_files(client):
    """The real grounded pipeline must not open AYTM/Tony/benchmark material."""
    created = client.post("/api/v1/studies", json={"study_mode": "neo_smart"}).json()["data"]["study"]
    study_id = created["study_id"]
    bootstrap = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/preset/neo")
    assert bootstrap.status_code == 200, bootstrap.text

    _install_audit_hook()
    _audit_state["hits"].clear()
    _audit_state["armed"] = True
    try:
        preview = _generate_candidates(client, study_id, count=15)
        selection = _patch_selection(
            client,
            study_id,
            preview["preview_id"],
            [{"candidate_id": c} for c in _candidate_ids(preview)[:5]],
        )
        assert selection.status_code == 200, selection.text
        finalized = client.post(f"/api/v1/studies/{study_id}/persona-set/finalize")
        assert finalized.status_code == 200, finalized.text
    finally:
        _audit_state["armed"] = False

    assert _audit_state["hits"] == [], (
        "candidate generation/selection opened withheld research files: "
        f"{_audit_state['hits']}"
    )
    assert preview["generation_mode"] == "grounded_priors"
