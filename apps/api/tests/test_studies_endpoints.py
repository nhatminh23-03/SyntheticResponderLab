from __future__ import annotations

from pathlib import Path


def _create_ready_to_run_study(client, study_mode: str = "neo_smart") -> str:
    created = client.post("/api/v1/studies", json={"study_mode": study_mode}).json()["data"]["study"]
    study_id = created["study_id"]

    audience_response = client.patch(
        f"/api/v1/studies/{study_id}/audience",
        json={
            "state": "California",
            "age_min": 30,
            "age_max": 60,
            "homeowner_only": True,
        },
    )
    assert audience_response.status_code == 200

    preset_response = client.post(f"/api/v1/studies/{study_id}/survey/preset/neo")
    assert preset_response.status_code == 200

    experiment_response = client.patch(
        f"/api/v1/studies/{study_id}/experiment",
        json={
            "sample_size": 80,
            "selected_models": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            "experiment_mode": "mirror",
            "reruns_per_persona": 1,
        },
    )
    assert experiment_response.status_code == 200

    return study_id


def test_create_study_endpoint(client):
    response = client.post("/api/v1/studies", json={"study_mode": "general"})

    assert response.status_code == 200
    study = response.json()["data"]["study"]
    assert study["study_id"].startswith("std_")
    assert study["study_mode"]["value"] == "general"
    assert study["study_mode"]["status"] == "saved"
    assert study["experiment"]["status"] == "not_started"
    assert study["lifecycle_status"] == "setup_in_progress"


def test_patch_study_mode_endpoint(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    response = client.patch(f"/api/v1/studies/{study_id}/study-mode", json={"study_mode": "neo_smart"})

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["study_mode"]["value"] == "neo_smart"
    assert payload["study_lifecycle_status"] == "setup_in_progress"


def test_bootstrap_neo_demo_endpoint_persists_ready_interview_setup(client, monkeypatch):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    monkeypatch.setattr(
        "src.services.study_service.preview_personas",
        lambda **kwargs: {
            "generation_mode": "grounded_priors",
            "grounded_priors_available": True,
            "cex_affordability_available": True,
            "prior_notes": [{"note": "Grounded priors active"}],
            "personas": [
                {
                    "persona_id": "neo-001",
                    "segment_label": "Backyard office homeowners",
                    "fit_tier": "strong",
                    "age_bucket": "35-44",
                    "income_bucket": "$75k-$124k",
                },
                {
                    "persona_id": "neo-002",
                    "segment_label": "Wellness-minded suburban households",
                    "fit_tier": "soft",
                    "age_bucket": "45-54",
                    "income_bucket": "$125k-$199k",
                },
            ],
        },
    )

    response = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/neo")

    assert response.status_code == 200
    payload = response.json()["data"]["study"]
    assert payload["study_mode"]["value"] == "neo_smart"
    assert payload["audience"]["status"] == "saved"
    assert payload["product"]["status"] == "saved"
    assert payload["product"]["value"]["product_name"] == "Tahoe Mini"
    assert payload["market"]["status"] == "saved"
    assert payload["survey"]["status"] == "saved"
    assert payload["survey"]["source_filename"] == "Neo Smart Living — Survey_HighPriority.md"
    assert payload["experiment"]["status"] == "saved"
    assert payload["experiment"]["value"]["sample_size"] == 100
    assert payload["experiment"]["value"]["experiment_mode"] == "split"
    assert payload["derived"]["workflow"]["ready_for_persona_preview"] is True
    assert payload["derived"]["latest_persona_preview"]["status"] == "completed"
    assert payload["derived"]["latest_persona_preview"]["request"]["sample_size"] == 12
    assert len(payload["derived"]["latest_persona_preview"]["personas"]) == 2
    assert payload["lifecycle_status"] == "persona_previewed"

    brief_response = client.get(f"/api/v1/studies/{study_id}/interview/brief")
    assert brief_response.status_code == 200
    brief_payload = brief_response.json()["data"]["research_brief"]
    assert brief_payload["status"] == "saved"
    assert "Tahoe Mini" in brief_payload["value"]["primary_question"]
    assert brief_payload["value"]["focus_fit_tiers"] == ["strong", "soft"]
    assert brief_payload["value"]["focus_segments"] == [
        "Backyard office homeowners",
        "Wellness-minded suburban households",
    ]

    latest_interview_response = client.get(
        f"/api/v1/studies/{study_id}/interview/runs/latest"
    )
    assert latest_interview_response.status_code == 200
    latest_interview_payload = latest_interview_response.json()["data"]["interview_run"]
    assert latest_interview_payload["status"] == "completed"
    assert latest_interview_payload["persona_count"] == 2
    assert len(latest_interview_payload["pairs"]) == 2
    assert latest_interview_payload["grounding_report"]["corpus_average"] > 0

    rerun_response = client.post(f"/api/v1/studies/{study_id}/interview/runs", json={})
    assert rerun_response.status_code == 200
    rerun_payload = rerun_response.json()["data"]["interview_run"]
    assert rerun_payload["status"] == "completed"
    assert rerun_payload["persona_count"] == 2

    insights_response = client.get(f"/api/v1/studies/{study_id}/interview/insights")
    assert insights_response.status_code == 200
    insights_payload = insights_response.json()["data"]["interview_insights"]
    assert insights_payload["available"] is True
    assert insights_payload["persona_count"] == 2
    assert len(insights_payload["themes"]) >= 1


def test_interview_chat_endpoint_continues_selected_persona(client, monkeypatch):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    monkeypatch.setattr(
        "src.services.study_service.preview_personas",
        lambda **kwargs: {
            "generation_mode": "grounded_priors",
            "grounded_priors_available": True,
            "cex_affordability_available": True,
            "prior_notes": [{"note": "Grounded priors active"}],
            "personas": [
                {
                    "persona_id": "neo-001",
                    "segment_label": "Backyard office homeowners",
                    "fit_tier": "strong",
                    "age_bucket": "35-44",
                    "income_bucket": "$75k-$124k",
                    "likely_use_case": "Dedicated home office",
                },
            ],
        },
    )

    bootstrap_response = client.post(f"/api/v1/studies/{study_id}/study-mode/bootstrap/neo")
    assert bootstrap_response.status_code == 200

    latest_interview_response = client.get(
        f"/api/v1/studies/{study_id}/interview/runs/latest"
    )
    assert latest_interview_response.status_code == 200
    latest_interview = latest_interview_response.json()["data"]["interview_run"]
    persona_id = latest_interview["pairs"][0]["persona_id"]

    client.app.state.settings.openrouter_api_key = "test-key"
    captured = {}

    def fake_call_openrouter_messages(**kwargs):
        captured.update(kwargs)
        return "I would move faster if the install felt predictable and the price included everything."

    monkeypatch.setattr(
        "src.services.interview_service._call_openrouter_messages",
        fake_call_openrouter_messages,
    )

    response = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            "persona_id": persona_id,
            "prompt": "What would make you more confident about buying?",
            "messages": [
                {
                    "role": "user",
                    "content": "Remind me what matters most in your decision?",
                },
                {
                    "role": "assistant",
                    "content": "I need to trust the install process and feel like I will use it every week.",
                },
            ],
            "transcript_source": "model_a",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]["interview_chat"]
    assert payload["persona_id"] == persona_id
    assert payload["transcript_source"] == "model_a"
    assert payload["reply"].startswith("I would move faster")
    assert payload["model"] == latest_interview["pairs"][0]["model_a"]["model"]
    assert captured["api_key"] == "test-key"
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][-1] == {
        "role": "user",
        "content": "What would make you more confident about buying?",
    }


def test_save_audience_and_get_workflow(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    audience_response = client.patch(
        f"/api/v1/studies/{study_id}/audience",
        json={
            "state": "California",
            "zip_code": "94105",
            "age_min": 25,
            "age_max": 64,
            "income_min": 50000,
            "income_max": 200000,
            "homeowner_only": True,
            "renter_only": False,
            "lifestyle_tags": ["remote work"],
            "home_type": "Single-family",
        },
    )

    assert audience_response.status_code == 200
    audience_payload = audience_response.json()["data"]
    assert audience_payload["audience"]["status"] == "saved"
    assert audience_payload["workflow"]["ready_for_persona_preview"] is False

    workflow_response = client.get(f"/api/v1/studies/{study_id}/workflow")

    assert workflow_response.status_code == 200
    workflow = workflow_response.json()["data"]["workflow"]
    assert workflow["ready_for_persona_preview"] is False
    experiment_stage = next(
        stage for stage in workflow["stages"] if stage["stage_key"] == "experiment"
    )
    assert experiment_stage["status"] == "blocked"
    assert "study_mode not saved" in experiment_stage["hard_blockers"]
    assert "product not saved" in experiment_stage["hard_blockers"]


def test_load_neo_survey_preset_endpoint(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    mode_response = client.patch(
        f"/api/v1/studies/{study_id}/study-mode",
        json={"study_mode": "neo_smart"},
    )
    assert mode_response.status_code == 200

    preset_response = client.post(f"/api/v1/studies/{study_id}/survey/preset/neo")

    assert preset_response.status_code == 200
    payload = preset_response.json()["data"]
    assert payload["survey"]["status"] == "saved"
    assert payload["survey"]["source_format"] == "md"
    assert payload["survey"]["question_count"] == 32
    assert payload["asset"]["original_filename"] == "Neo Smart Living — Survey_HighPriority.md"


def test_upload_aytm_docx_succeeds_with_fallback_parser(client):
    workspace_root = Path(__file__).resolve().parents[3]
    docx_path = (
        workspace_root
        / "NeoSmart-Hackathon-App"
        / "Provided Info"
        / "aytm Survey #760085  (Neo Smart Living — Tahoe Mini Survey).docx"
    )

    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    with docx_path.open("rb") as handle:
        response = client.post(
            f"/api/v1/studies/{study_id}/survey/upload",
            files={
                "file": (
                    docx_path.name,
                    handle.read(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["survey"]["status"] == "saved"
    assert payload["survey"]["source_format"] == "docx"
    assert payload["survey"]["question_count"] >= 20
    warnings = payload["survey"]["parse_warnings"]
    assert any("DOCX fallback parser used" in warning for warning in warnings)


def test_save_experiment_endpoint(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    response = client.patch(
        f"/api/v1/studies/{study_id}/experiment",
        json={
            "sample_size": 120,
            "selected_models": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            "experiment_mode": "split",
            "reruns_per_persona": 1,
            "notes": "Compare two starter models.",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["experiment"]["status"] == "saved"
    assert payload["experiment"]["value"]["experiment_mode"] == "split"
    assert payload["experiment"]["value"]["split_across_models"] is True
    assert payload["workflow"]["ready_for_persona_preview"] is False


def test_persona_preview_requires_saved_experiment(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    audience_response = client.patch(
        f"/api/v1/studies/{study_id}/audience",
        json={
            "age_min": 25,
            "age_max": 54,
        },
    )
    assert audience_response.status_code == 200

    response = client.post(
        f"/api/v1/studies/{study_id}/personas/preview",
        json={"sample_size": 8},
    )

    assert response.status_code == 409
    assert "Experiment plan must be saved" in response.json()["error"]["message"]


def test_persona_preview_happy_path_updates_canonical_study(client, monkeypatch):
    created = client.post(
        "/api/v1/studies", json={"study_mode": "neo_smart"}
    ).json()["data"]["study"]
    study_id = created["study_id"]

    audience_response = client.patch(
        f"/api/v1/studies/{study_id}/audience",
        json={
            "state": "California",
            "age_min": 30,
            "age_max": 60,
            "homeowner_only": True,
        },
    )
    assert audience_response.status_code == 200

    product_response = client.patch(
        f"/api/v1/studies/{study_id}/product",
        json={
            "business_name": "Neo Smart Living",
            "product_name": "Tahoe Mini",
            "product_description": "Compact backyard modular studio.",
            "product_type": "Permit-light backyard studio",
            "price_range": "$23,000 delivered and installed",
        },
    )
    assert product_response.status_code == 200

    market_response = client.patch(
        f"/api/v1/studies/{study_id}/market",
        json={
            "category": "Backyard prefab studio",
            "substitutes": ["Traditional shed"],
        },
    )
    assert market_response.status_code == 200

    preset_response = client.post(f"/api/v1/studies/{study_id}/survey/preset/neo")
    assert preset_response.status_code == 200

    experiment_response = client.patch(
        f"/api/v1/studies/{study_id}/experiment",
        json={
            "sample_size": 80,
            "selected_models": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            "experiment_mode": "mirror",
            "reruns_per_persona": 1,
        },
    )
    assert experiment_response.status_code == 200
    assert experiment_response.json()["data"]["workflow"]["ready_for_persona_preview"] is True

    monkeypatch.setattr(
        "src.services.study_service.preview_personas",
        lambda **kwargs: {
            "generation_mode": "grounded_priors",
            "grounded_priors_available": True,
            "cex_affordability_available": True,
            "prior_notes": [{"note": "Grounded priors active"}],
            "personas": [
                {
                    "persona_id": "neo-001",
                    "segment_label": "Backyard office homeowners",
                    "fit_tier": "high",
                    "age_band": "35-44",
                    "income_band": "$75k-$124k",
                },
                {
                    "persona_id": "neo-002",
                    "segment_label": "Wellness-minded suburban households",
                    "fit_tier": "medium",
                    "age_band": "45-54",
                    "income_band": "$125k-$199k",
                },
            ],
        },
    )

    preview_response = client.post(
        f"/api/v1/studies/{study_id}/personas/preview",
        json={"sample_size": 2},
    )

    assert preview_response.status_code == 200
    preview_payload = preview_response.json()["data"]["persona_preview"]
    assert preview_payload["status"] == "completed"
    assert len(preview_payload["personas"]) == 2

    study_response = client.get(f"/api/v1/studies/{study_id}")
    assert study_response.status_code == 200
    study_payload = study_response.json()["data"]["study"]
    assert study_payload["experiment"]["status"] == "saved"
    assert study_payload["derived"]["latest_persona_preview"]["preview_id"].startswith("ppr_")
    assert study_payload["derived"]["workflow"]["ready_for_persona_preview"] is True


def test_general_mode_partial_setup_rehydrates_correctly(client):
    created = client.post(
        "/api/v1/studies", json={"study_mode": "general"}
    ).json()["data"]["study"]
    study_id = created["study_id"]

    audience_response = client.patch(
        f"/api/v1/studies/{study_id}/audience",
        json={
            "state": "Washington",
            "age_min": 28,
            "age_max": 58,
            "income_min": 70000,
            "income_max": 180000,
        },
    )
    assert audience_response.status_code == 200

    product_response = client.patch(
        f"/api/v1/studies/{study_id}/product",
        json={
            "business_name": "Custom Backyard Labs",
            "product_name": "Studio One",
            "product_description": "Modular backyard office suite.",
        },
    )
    assert product_response.status_code == 200

    study_response = client.get(f"/api/v1/studies/{study_id}")
    assert study_response.status_code == 200
    payload = study_response.json()["data"]["study"]
    assert payload["study_mode"]["value"] == "general"
    assert payload["audience"]["status"] == "saved"
    assert payload["product"]["status"] == "saved"
    assert payload["market"]["status"] == "not_started"
    assert payload["survey"]["status"] == "not_started"
    assert payload["experiment"]["status"] == "not_started"
    assert payload["derived"]["workflow"]["next_recommended_stage"] == "market"


def test_product_provider_gaps_fail_clearly(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    url_response = client.post(
        f"/api/v1/studies/{study_id}/product/url-autofill",
        json={"url": "https://example.com/product", "apply_to_product": False},
    )
    assert url_response.status_code == 503
    assert "OPENROUTER_API_KEY is required" in url_response.json()["error"]["message"]

    image_response = client.post(
        f"/api/v1/studies/{study_id}/product/image-analysis",
        files={"file": ("product.png", b"fake-image-bytes", "image/png")},
    )
    assert image_response.status_code == 503
    assert "Google Vision credentials are required" in image_response.json()["error"]["message"]


def test_model_catalog_endpoint_returns_fallback_when_provider_missing(client):
    response = client.get("/api/v1/models")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["source"] == "fallback"
    assert len(payload["models"]) >= 2
    assert payload["warning"]


def test_start_simulation_run_endpoint_returns_saved_job(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)

    monkeypatch.setattr(
        "src.services.study_service.execute_simulation_run",
        lambda **kwargs: {
            "run_id": "run_demo_001",
            "status": "completed",
            "total_requested_responses": 80,
            "total_generated_responses": 80,
            "models_used": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            "experiment_mode": "mirror",
            "survey_title": "Neo Smart Living Demo Survey",
            "question_count": 32,
            "generation_mode": "mock",
            "run_conditions": {
                "context_influence": {"enabled": True, "sources": ["audience", "product", "market"]},
                "generation_mode": "mock",
                "selected_models": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            },
            "personas": [
                {
                    "persona_id": "neo-001",
                    "segment_label": "Backyard office homeowners",
                    "fit_tier": "high",
                }
            ],
            "response_record_preview": [
                {
                    "respondent_id": "neo-001",
                    "question_id": "Q1",
                    "question_text": "How interested are you?",
                    "answer": "Very interested",
                    "model": "openai/gpt-4o-mini",
                }
            ],
            "response_records": [],
            "warnings": [],
            "survey_parse_warnings": ["Parser note example"],
        },
    )

    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["simulation_run"]["status"] == "completed"
    assert payload["simulation_run"]["result"]["run_id"] == "run_demo_001"
    assert payload["simulation_run"]["result"]["survey_title"] == "Neo Smart Living Demo Survey"

    latest_response = client.get(f"/api/v1/studies/{study_id}/simulation-runs/latest")
    assert latest_response.status_code == 200
    latest_payload = latest_response.json()["data"]
    assert latest_payload["simulation_run"]["job_type"] == "simulation_run"
    assert latest_payload["simulation_run"]["result"]["total_generated_responses"] == 80


def test_clear_latest_simulation_run_endpoint_removes_saved_jobs(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)

    monkeypatch.setattr(
        "src.services.study_service.execute_simulation_run",
        lambda **kwargs: {
            "run_id": "run_demo_clear",
            "status": "completed",
            "total_requested_responses": 80,
            "total_generated_responses": 80,
            "models_used": ["openai/gpt-4o-mini"],
            "experiment_mode": "mirror",
            "survey_title": "Neo Smart Living Demo Survey",
            "question_count": 32,
            "generation_mode": "mock",
            "run_conditions": {
                "context_influence": {"enabled": True, "sources": ["audience"]},
                "generation_mode": "mock",
                "selected_models": ["openai/gpt-4o-mini"],
            },
            "personas": [],
            "response_record_preview": [],
            "response_records": [],
            "warnings": [],
            "survey_parse_warnings": [],
        },
    )

    start_response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert start_response.status_code == 200

    clear_response = client.delete(f"/api/v1/studies/{study_id}/simulation-runs/latest")
    assert clear_response.status_code == 200
    assert clear_response.json()["data"]["cleared"] >= 1

    latest_response = client.get(f"/api/v1/studies/{study_id}/simulation-runs/latest")
    assert latest_response.status_code == 200
    assert latest_response.json()["data"]["simulation_run"] is None


def test_start_stability_check_endpoint_returns_saved_job(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)

    monkeypatch.setattr(
        "src.services.study_service.execute_stability_check",
        lambda **kwargs: {
            "repeat_runs": 3,
            "run_summaries": [{"run_index": 1}, {"run_index": 2}, {"run_index": 3}],
            "stability_table": [
                {
                    "metric_name": "overall_alignment",
                    "stability_label": "stable",
                    "run_1": 0.91,
                    "run_2": 0.9,
                    "run_3": 0.92,
                }
            ],
            "stability_labels": ["stable"],
            "warnings": [],
            "used_grounded_priors": True,
            "created_at": "2026-03-28T00:00:00Z",
        },
    )

    response = client.post(
        f"/api/v1/studies/{study_id}/simulation-runs/stability",
        json={"repeat_runs": 3},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["stability_check"]["status"] == "completed"
    assert payload["stability_check"]["result"]["repeat_runs"] == 3

    latest_response = client.get(f"/api/v1/studies/{study_id}/simulation-runs/stability/latest")
    assert latest_response.status_code == 200
    latest_payload = latest_response.json()["data"]
    assert latest_payload["stability_check"]["job_type"] == "simulation_stability"
    assert latest_payload["stability_check"]["result"]["stability_labels"] == ["stable"]


def test_analysis_endpoint_returns_summary_and_question_explorer(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)

    monkeypatch.setattr(
        "src.services.study_service.execute_simulation_run",
        lambda **kwargs: {
            "run_id": "run_analysis_001",
            "status": "completed",
            "total_requested_responses": 4,
            "total_generated_responses": 4,
            "models_used": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            "experiment_mode": "mirror",
            "survey_title": "Neo Smart Living Demo Survey",
            "question_count": 2,
            "generation_mode": "mock",
            "warnings": [],
            "survey_parse_warnings": ["Expanded matrix question example"],
            "personas": [
                {"persona_id": "PERS_001", "segment_label": "Remote Professionals", "fit_tier": "strong"},
                {"persona_id": "PERS_002", "segment_label": "Wellness-Oriented", "fit_tier": "strong"},
            ],
            "response_record_preview": [],
            "response_records": [
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q1",
                    "question_text": "How interested are you in Tahoe Mini?",
                    "question_type": "likert",
                    "answer": 5,
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q1",
                    "question_text": "How interested are you in Tahoe Mini?",
                    "question_type": "likert",
                    "answer": 4,
                    "segment_label": "Wellness-Oriented",
                },
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q2",
                    "question_text": "Why did you choose that answer?",
                    "question_type": "open_text",
                    "answer": "It feels like a realistic home office upgrade.",
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q2",
                    "question_text": "Why did you choose that answer?",
                    "question_type": "open_text",
                    "answer": "I like the flexibility and backyard fit.",
                    "segment_label": "Wellness-Oriented",
                },
            ],
        },
    )

    start_response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert start_response.status_code == 200

    analysis_response = client.get(f"/api/v1/studies/{study_id}/analysis")

    assert analysis_response.status_code == 200
    payload = analysis_response.json()["data"]["analysis"]
    assert payload["available"] is True
    assert payload["summary"]["total_records"] == 4
    assert payload["run"]["run_id"] == "run_analysis_001"
    assert payload["filters"]["selected_question_id"] == "Q1"
    assert payload["question_explorer"]["question_id"] == "Q1"
    assert payload["benchmark_snapshot"]["available"] is True
    assert payload["realism_scorecard"]["available"] is True
    assert payload["open_text"]["available"] is True
    assert payload["records_preview"]["total"] == 4


def test_insights_endpoint_returns_executive_summary_and_charts(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)

    monkeypatch.setattr(
        "src.services.study_service.execute_simulation_run",
        lambda **kwargs: {
            "run_id": "run_insights_001",
            "status": "completed",
            "total_requested_responses": 8,
            "total_generated_responses": 8,
            "models_used": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            "experiment_mode": "mirror",
            "survey_title": "Neo Smart Living Demo Survey",
            "question_count": 8,
            "generation_mode": "mock",
            "warnings": [],
            "survey_parse_warnings": [],
            "personas": [
                {"persona_id": "PERS_001", "segment_label": "Remote Professionals", "fit_tier": "strong"},
                {"persona_id": "PERS_002", "segment_label": "Wellness-Oriented", "fit_tier": "strong"},
            ],
            "response_record_preview": [],
            "response_records": [
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "S3",
                    "question_text": "Outdoor space feasibility",
                    "question_type": "single_choice",
                    "answer": "Yes, definitely",
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "S3",
                    "question_text": "Outdoor space feasibility",
                    "question_type": "single_choice",
                    "answer": "Yes, likely",
                    "segment_label": "Wellness-Oriented",
                },
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q1",
                    "question_text": "Purchase interest at $23,000",
                    "question_type": "likert",
                    "answer": 5,
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q1",
                    "question_text": "Purchase interest at $23,000",
                    "question_type": "likert",
                    "answer": 4,
                    "segment_label": "Wellness-Oriented",
                },
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q2",
                    "question_text": "Purchase likelihood in 24 months",
                    "question_type": "likert",
                    "answer": 4,
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q2",
                    "question_text": "Purchase likelihood in 24 months",
                    "question_type": "likert",
                    "answer": 3,
                    "segment_label": "Wellness-Oriented",
                },
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q3",
                    "question_text": "Primary intended use",
                    "question_type": "single_choice",
                    "answer": "Home office",
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q3",
                    "question_text": "Primary intended use",
                    "question_type": "single_choice",
                    "answer": "Home gym",
                    "segment_label": "Wellness-Oriented",
                },
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q5_1",
                    "question_text": "Barrier: Upfront price",
                    "question_type": "likert",
                    "answer": 5,
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q5_1",
                    "question_text": "Barrier: Upfront price",
                    "question_type": "likert",
                    "answer": 4,
                    "segment_label": "Wellness-Oriented",
                },
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q5_2",
                    "question_text": "Barrier: Permitting uncertainty",
                    "question_type": "likert",
                    "answer": 3,
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q5_2",
                    "question_text": "Barrier: Permitting uncertainty",
                    "question_type": "likert",
                    "answer": 2,
                    "segment_label": "Wellness-Oriented",
                },
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q10A",
                    "question_text": "Concept 10 appeal",
                    "question_type": "likert",
                    "answer": 5,
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q10A",
                    "question_text": "Concept 10 appeal",
                    "question_type": "likert",
                    "answer": 4,
                    "segment_label": "Wellness-Oriented",
                },
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q10B",
                    "question_text": "Concept 10 purchase likelihood",
                    "question_type": "likert",
                    "answer": 4,
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q10B",
                    "question_text": "Concept 10 purchase likelihood",
                    "question_type": "likert",
                    "answer": 3,
                    "segment_label": "Wellness-Oriented",
                },
            ],
        },
    )

    start_response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert start_response.status_code == 200

    insights_response = client.get(f"/api/v1/studies/{study_id}/insights")

    assert insights_response.status_code == 200
    payload = insights_response.json()["data"]["insights"]
    assert payload["available"] is True
    assert payload["executive_summary"]["top_use_case"]["label"] in {"Home office", "Home gym"}
    assert payload["charts"]["barrier_ranking"]["available"] is True
    assert payload["charts"]["message_performance"]["available"] is True
    assert payload["charts"]["interest_ladder"]["available"] is True
    assert payload["charts"]["segment_heatmap"]["available"] is True
    assert payload["charts"]["model_difference"]["available"] is True
    assert len(payload["top_findings"]) >= 3
    assert len(payload["recommendations"]) >= 2
