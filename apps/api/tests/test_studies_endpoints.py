from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from src.persistence.models import InterviewTurn, Persona, Study
from src.persistence.persona_seed import load_persona_seed_rows
from src.services.interview_service import OpenRouterChatResult


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


def _mock_insights_run_payload() -> dict:
    return {
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
    }


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
    provider_call_count = 0

    def fake_call_openrouter_messages(**kwargs):
        nonlocal provider_call_count
        provider_call_count += 1
        captured.update(kwargs)
        return OpenRouterChatResult(
            text="I would move faster if the install felt predictable and the price included everything.",
            model=kwargs["model"],
            tokens_in=347,
            tokens_out=19,
            cost_usd=Decimal("0.000184250000"),
        )

    monkeypatch.setattr(
        "src.services.interview_service._call_openrouter_messages",
        fake_call_openrouter_messages,
    )

    first_question = {
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
    }
    response = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json=first_question,
    )

    assert response.status_code == 200
    payload = response.json()["data"]["interview_chat"]
    assert payload["persona_id"] == persona_id
    assert payload["transcript_source"] == "model_a"
    assert payload["reply"].startswith("I would move faster")
    assert payload["model"] == latest_interview["pairs"][0]["model_a"]["model"]
    assert payload["session_id"].startswith("ses_")
    assert payload["cache_hit"] is False
    assert payload["session_usage"] == {
        "tokens_in": 347,
        "tokens_out": 19,
        "cost_usd": "0.00018425",
    }
    assert provider_call_count == 1
    assert captured["api_key"] == "test-key"
    assert captured["messages"][0]["role"] == "system"
    assert '"fit_tier"' not in captured["messages"][0]["content"]
    assert '"likely_use_case": "Dedicated home office"' in captured["messages"][0]["content"]
    assert captured["messages"][-1] == {
        "role": "user",
        "content": "What would make you more confident about buying?",
    }

    client.app.state.settings.openrouter_api_key = ""
    repeated_response = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json=first_question,
    )
    assert repeated_response.status_code == 200
    repeated_payload = repeated_response.json()["data"]["interview_chat"]
    assert repeated_payload["reply"] == payload["reply"]
    assert repeated_payload["cache_hit"] is True
    assert repeated_payload["session_usage"] == {
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": "0",
    }
    assert repeated_payload["session_id"] != payload["session_id"]
    assert provider_call_count == 1

    client.app.state.settings.openrouter_api_key = "test-key"

    over_budget_preflight = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            **first_question,
            "prompt": "What else would make this purchase impossible?",
            # This session currently contains only a free cache hit. Its first
            # paid call must still go through the run preflight.
            "session_id": repeated_payload["session_id"],
            "estimated_run_cost_usd": "0.7501",
        },
    )
    assert over_budget_preflight.status_code == 429
    preflight_error = over_budget_preflight.json()["error"]
    assert preflight_error["code"] == "quota_exceeded"
    assert "would cost $0.76" in preflight_error["message"]
    assert provider_call_count == 1

    followup_response = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            "persona_id": persona_id,
            "prompt": "What would predictable installation look like?",
            "messages": [
                {
                    "role": "user",
                    "content": "What would make you more confident about buying?",
                },
                {"role": "assistant", "content": payload["reply"]},
            ],
            "transcript_source": "model_a",
            "session_id": payload["session_id"],
        },
    )
    assert followup_response.status_code == 200
    followup_payload = followup_response.json()["data"]["interview_chat"]
    assert followup_payload["session_id"] == payload["session_id"]
    assert followup_payload["cache_hit"] is False
    assert followup_payload["session_usage"] == {
        "tokens_in": 694,
        "tokens_out": 38,
        "cost_usd": "0.00036850",
    }
    assert provider_call_count == 2

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        turns = session.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == payload["session_id"])
            .order_by(InterviewTurn.created_at, InterviewTurn.id)
        ).all()

    assert [(turn.role, turn.text) for turn in turns] == [
        ("user", "What would make you more confident about buying?"),
        (
            "assistant",
            "I would move faster if the install felt predictable and the price included everything.",
        ),
        ("user", "What would predictable installation look like?"),
        (
            "assistant",
            "I would move faster if the install felt predictable and the price included everything.",
        ),
    ]
    assert all(turn.study_id is not None for turn in turns)
    assert all(turn.persona_id == persona_id for turn in turns)
    assert all(turn.model == payload["model"] for turn in turns)
    assert [(turn.tokens_in, turn.tokens_out, turn.cost_usd) for turn in turns] == [
        (0, 0, Decimal("0E-18")),
        (347, 19, Decimal("0.000184250000000000")),
        (0, 0, Decimal("0E-18")),
        (347, 19, Decimal("0.000184250000000000")),
    ]

    measured_session_spend = Decimal("0.000368500000")
    client.app.state.settings.llm_budget_usd = measured_session_spend
    run_hard_stop = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            **first_question,
            "prompt": "Can you add one more concern?",
            "session_id": payload["session_id"],
        },
    )
    assert run_hard_stop.status_code == 429
    assert run_hard_stop.json()["error"]["details"]["scope"] == "run"
    assert provider_call_count == 2

    client.app.state.settings.llm_budget_usd = measured_session_spend + Decimal("0.0001")
    measured_overage = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            **first_question,
            "prompt": "Could one last concern fit in the remaining budget?",
            "session_id": payload["session_id"],
        },
    )
    assert measured_overage.status_code == 429
    assert measured_overage.json()["error"]["details"]["measured_cost_usd"] == "0.000184250000"
    assert measured_overage.json()["error"]["details"]["session_id"] == payload["session_id"]
    assert measured_overage.json()["error"]["details"]["session_usage"] == {
        "tokens_in": 1041,
        "tokens_out": 57,
        "cost_usd": "0.00055275",
    }
    assert provider_call_count == 3

    blocked_after_overage = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            **first_question,
            "prompt": "This second overage must not reach the provider.",
            "session_id": payload["session_id"],
        },
    )
    assert blocked_after_overage.status_code == 429
    assert provider_call_count == 3

    spend_after_overage = measured_session_spend + Decimal("0.000184250000")
    client.app.state.settings.llm_budget_usd = spend_after_overage / 30
    class_hard_stop = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            **first_question,
            "prompt": "Which new issue should the whole class consider?",
        },
    )
    assert class_hard_stop.status_code == 429
    assert class_hard_stop.json()["error"]["details"]["scope"] == "class"
    assert provider_call_count == 3

    client.app.state.settings.llm_budget_usd = Decimal("0")
    kill_switch_stop = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            **first_question,
            "prompt": "Should this paid request be disabled?",
        },
    )
    assert kill_switch_stop.status_code == 429
    assert "Budget hard stop" in kill_switch_stop.json()["error"]["message"]
    assert provider_call_count == 3

    client.app.state.settings.llm_budget_usd = Decimal("0.0001")
    first_call_overage = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            **first_question,
            "prompt": "Can a newly started session exceed its first-call budget?",
        },
    )
    assert first_call_overage.status_code == 429
    first_call_error = first_call_overage.json()["error"]
    over_budget_session_id = first_call_error["details"]["session_id"]
    assert over_budget_session_id.startswith("ses_")
    assert first_call_error["details"]["session_usage"] == {
        "tokens_in": 347,
        "tokens_out": 19,
        "cost_usd": "0.00018425",
    }
    assert provider_call_count == 4

    retry_over_budget_session = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            **first_question,
            "prompt": "This retry must retain the generated session and stop before charging.",
            "session_id": over_budget_session_id,
        },
    )
    assert retry_over_budget_session.status_code == 429
    assert retry_over_budget_session.json()["error"]["details"]["scope"] == "run"
    assert provider_call_count == 4

    client.app.state.settings.llm_budget_usd = Decimal("0.75")

    with session_factory() as session:
        repeated_turns = session.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == repeated_payload["session_id"])
            .order_by(InterviewTurn.created_at, InterviewTurn.id)
        ).all()
    assert [(turn.role, turn.tokens_in, turn.tokens_out, turn.cost_usd) for turn in repeated_turns] == [
        ("user", 0, 0, Decimal("0E-18")),
        ("assistant", 0, 0, Decimal("0E-18")),
    ]

    client.app.state.settings.cache_mode = "replay_only"
    replay_miss_response = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            **first_question,
            "prompt": "Which entirely new concern should we discuss?",
        },
    )
    assert replay_miss_response.status_code == 409
    assert "CACHE_MODE=replay_only" in replay_miss_response.json()["error"]["message"]
    assert provider_call_count == 4


def test_interview_chat_endpoint_supports_standalone_fixed_personas(
    client,
    db_session,
    monkeypatch,
):
    persona_row = load_persona_seed_rows()[0]
    db_session.add(Persona(**persona_row))
    db_session.commit()
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    client.app.state.settings.openrouter_api_key = "test-key"
    provider_calls: list[dict] = []

    def fake_call_openrouter_messages(**kwargs):
        provider_calls.append(kwargs)
        return OpenRouterChatResult(
            text="I would first want to understand the total installed cost.",
            model=kwargs["model"],
            tokens_in=210,
            tokens_out=14,
            cost_usd=Decimal("0.0001"),
        )

    monkeypatch.setattr(
        "src.services.interview_service._call_openrouter_messages",
        fake_call_openrouter_messages,
    )
    request_payload = {
        "persona_id": persona_row["persona_id"],
        "prompt": "What would you need to know first?",
        "messages": [
            {"role": "user", "content": "What is your first reaction?"},
            {"role": "assistant", "content": "I like the idea, but I would be cautious."},
        ],
        "model": "openai/gpt-4o-mini",
        "session_id": None,
        "standalone": True,
        "allow_expensive_models": False,
    }

    response = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json=request_payload,
    )

    assert response.status_code == 200
    payload = response.json()["data"]["interview_chat"]
    assert payload["persona_id"] == persona_row["persona_id"]
    assert payload["transcript_source"] == "standalone"
    assert payload["source_run_id"] is None
    assert payload["session_id"].startswith("ses_")
    assert payload["reply"].startswith("I would first want")
    assert payload["session_usage"] == {
        "tokens_in": 210,
        "tokens_out": 14,
        "cost_usd": "0.0001",
    }
    assert payload["system_prompt"] == provider_calls[0]["messages"][0]["content"]
    assert "fit_tier" not in payload["system_prompt"]
    assert provider_calls[0]["messages"][-3:] == [
        {"role": "user", "content": "What is your first reaction?"},
        {"role": "assistant", "content": "I like the idea, but I would be cautious."},
        {"role": "user", "content": "What would you need to know first?"},
    ]

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        persisted_turns = session.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == payload["session_id"])
            .order_by(InterviewTurn.created_at, InterviewTurn.id)
        ).all()
    assert [(turn.role, turn.text) for turn in persisted_turns] == [
        ("user", "What would you need to know first?"),
        ("assistant", "I would first want to understand the total installed cost."),
    ]

    unknown_model = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={**request_payload, "model": "provider/not-curated"},
    )
    assert unknown_model.status_code == 400
    assert "curated interview catalog" in unknown_model.json()["error"]["message"]

    expensive_without_opt_in = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={**request_payload, "model": "anthropic/claude-sonnet-4.5"},
    )
    assert expensive_without_opt_in.status_code == 400
    assert "require opt-in" in expensive_without_opt_in.json()["error"]["message"]
    assert len(provider_calls) == 1


def test_standalone_chat_cannot_understate_estimate_to_bypass_class_budget(
    client,
    db_session,
    monkeypatch,
):
    persona_row = load_persona_seed_rows()[0]
    db_session.add(Persona(**persona_row))
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    study = db_session.scalar(select(Study).where(Study.public_id == study_id))
    assert study is not None
    db_session.add(
        InterviewTurn(
            study_id=study.id,
            persona_id=persona_row["persona_id"],
            session_id="ses_existing_class_spend",
            role="assistant",
            text="Previously billed answer.",
            model="openai/gpt-4o-mini",
            tokens_in=1,
            tokens_out=1,
            cost_usd=Decimal("0.29995"),
        )
    )
    db_session.commit()

    client.app.state.settings.llm_budget_usd = Decimal("0.01")
    client.app.state.settings.openrouter_api_key = "test-key"
    provider_calls: list[dict] = []

    def fake_call_openrouter_messages(**kwargs):
        provider_calls.append(kwargs)
        return OpenRouterChatResult(
            text="This call should never be made.",
            model=kwargs["model"],
            tokens_in=10,
            tokens_out=2,
            cost_usd=Decimal("0.0001"),
        )

    monkeypatch.setattr(
        "src.services.interview_service._call_openrouter_messages",
        fake_call_openrouter_messages,
    )

    response = client.post(
        f"/api/v1/studies/{study_id}/interview/chat",
        json={
            "persona_id": persona_row["persona_id"],
            "prompt": "Can I bypass the class preflight?",
            "model": "openai/gpt-4o-mini",
            "session_id": None,
            "estimated_run_cost_usd": "0",
            "standalone": True,
        },
    )

    assert response.status_code == 429
    assert response.json()["error"]["details"]["scope"] == "class"
    assert provider_calls == []


def test_interview_comparison_is_budgeted_cached_and_persisted(client, db_session, monkeypatch):
    persona_row = load_persona_seed_rows()[0]
    db_session.add(Persona(**persona_row))
    db_session.commit()
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    client.app.state.settings.openrouter_api_key = "test-key"
    provider_models: list[str] = []
    provider_messages: list[list[dict[str, str]]] = []

    def fake_call_openrouter_messages(**kwargs):
        provider_models.append(kwargs["model"])
        provider_messages.append(kwargs["messages"])
        return OpenRouterChatResult(
            text=f"Answer from {kwargs['model']}",
            model=kwargs["model"],
            tokens_in=100,
            tokens_out=20,
            cost_usd=Decimal("0.001"),
        )

    monkeypatch.setattr(
        "src.services.interview_service._call_openrouter_messages",
        fake_call_openrouter_messages,
    )
    request_payload = {
        "persona_id": persona_row["persona_id"],
        "question": "What matters most to you?",
        "model_ids": ["google/gemini-2.5-flash-lite", "openai/gpt-4o-mini"],
        "allow_expensive_models": False,
    }

    response = client.post(
        f"/api/v1/studies/{study_id}/interview/compare",
        json=request_payload,
    )

    assert response.status_code == 200
    comparison = response.json()["data"]["interview_comparison"]
    assert comparison["persona_id"] == persona_row["persona_id"]
    assert comparison["question"] == request_payload["question"]
    assert [result["model_id"] for result in comparison["results"]] == request_payload["model_ids"]
    assert all(result["error"] is None for result in comparison["results"])
    assert all(
        result["post_interview_score"] == {
            "fit_tier": "latent",
            "emotional_classification": "neutral",
            "label": "scored after the interview, never before",
        }
        for result in comparison["results"]
    )
    assert comparison["session_usage"] == {
        "tokens_in": 200,
        "tokens_out": 40,
        "cost_usd": "0.002",
    }
    assert provider_models == request_payload["model_ids"]
    assert all(messages[-1]["content"] == request_payload["question"] for messages in provider_messages)
    assert all('"fit_tier"' not in messages[0]["content"] for messages in provider_messages)

    session_factory = client.app.state.session_factory
    with session_factory() as session:
        turns = session.scalars(
            select(InterviewTurn).where(
                InterviewTurn.session_id == comparison["session_id"]
            )
        ).all()
    assert len(turns) == 4
    assert {turn.study_id for turn in turns} == {turns[0].study_id}
    assert {turn.persona_id for turn in turns} == {persona_row["persona_id"]}

    # A repeat uses the shared cache even with the zero-dollar kill switch.
    client.app.state.settings.llm_budget_usd = Decimal("0")
    repeated = client.post(
        f"/api/v1/studies/{study_id}/interview/compare",
        json=request_payload,
    )
    assert repeated.status_code == 200
    repeated_comparison = repeated.json()["data"]["interview_comparison"]
    assert all(result["cache_hit"] is True for result in repeated_comparison["results"])
    assert repeated_comparison["session_usage"]["cost_usd"] == "0"
    assert provider_models == request_payload["model_ids"]

    expensive_without_opt_in = client.post(
        f"/api/v1/studies/{study_id}/interview/compare",
        json={
            **request_payload,
            "model_ids": ["google/gemini-2.5-flash-lite", "google/gemini-2.5-pro"],
        },
    )
    assert expensive_without_opt_in.status_code == 400
    assert "require opt-in" in expensive_without_opt_in.json()["error"]["message"]
    assert provider_models == request_payload["model_ids"]

    blocked = client.post(
        f"/api/v1/studies/{study_id}/interview/compare",
        json={**request_payload, "question": "A new paid comparison?"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "quota_exceeded"
    assert provider_models == request_payload["model_ids"]


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
    docx_path = (
        Path(client.app.state.settings.legacy_app_root)
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
                    "fit_tier": "strong",
                    "age_band": "35-44",
                    "income_band": "$75k-$124k",
                },
                {
                    "persona_id": "neo-002",
                    "segment_label": "Wellness-minded suburban households",
                    "fit_tier": "soft",
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


def test_product_url_autofill_rejects_private_network_targets(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    response = client.post(
        f"/api/v1/studies/{study_id}/product/url-autofill",
        json={"url": "http://127.0.0.1/internal", "apply_to_product": False},
    )

    assert response.status_code == 400
    assert "private-network URLs are not allowed" in response.json()["error"]["message"]


def test_product_url_autofill_accepts_public_https_url(client, monkeypatch):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    monkeypatch.setattr(
        "src.services.study_service.product_url_autofill",
        lambda **kwargs: {
            "input_url": kwargs["url"],
            "page_text": "Public product page copy",
            "product_patch": {
                "business_name": "Example Co",
                "product_name": "Example Product",
                "product_description": "Autofilled from a public product page.",
            },
        },
    )

    response = client.post(
        f"/api/v1/studies/{study_id}/product/url-autofill",
        json={"url": "https://example.com/product", "apply_to_product": False},
    )

    assert response.status_code == 200
    assert response.json()["data"]["enrichment"]["input_url"] == "https://example.com/product"


def test_survey_upload_rejects_oversized_payload(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]
    client.app.state.settings.max_survey_upload_bytes = 16

    response = client.post(
        f"/api/v1/studies/{study_id}/survey/upload",
        files={"file": ("survey.md", b"x" * 17, "text/markdown")},
    )

    assert response.status_code == 413
    assert "Survey upload exceeds" in response.json()["error"]["message"]


def test_survey_upload_rejects_unsupported_extension_before_read(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    response = client.post(
        f"/api/v1/studies/{study_id}/survey/upload",
        files={"file": ("survey.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 415
    assert "Unsupported survey file type" in response.json()["error"]["message"]


def test_product_image_analysis_rejects_oversized_payload(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]
    client.app.state.settings.max_product_image_upload_bytes = 8

    response = client.post(
        f"/api/v1/studies/{study_id}/product/image-analysis",
        files={"file": ("product.png", b"123456789", "image/png")},
    )

    assert response.status_code == 413
    assert "Product image upload exceeds" in response.json()["error"]["message"]


def test_product_image_analysis_rejects_unsupported_extension_before_read(client):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    response = client.post(
        f"/api/v1/studies/{study_id}/product/image-analysis",
        files={"file": ("product.gif", b"GIF89a", "image/gif")},
    )

    assert response.status_code == 415
    assert "Unsupported image type" in response.json()["error"]["message"]


def test_product_image_analysis_accepts_small_png_upload(client, monkeypatch):
    created = client.post("/api/v1/studies", json={}).json()["data"]["study"]
    study_id = created["study_id"]

    monkeypatch.setattr(
        "src.api.studies.handle_product_image_analysis",
        lambda db, settings, study, filename, content_type, file_bytes, apply_to_product: {
            "image_analysis": {
                "status": "completed",
                "source_asset_id": "asset_demo",
                "analysis": {"labels": ["studio"]},
                "proposed_product_patch": None,
                "warnings": [],
                "applied_to_product": apply_to_product,
            }
        },
    )

    response = client.post(
        f"/api/v1/studies/{study_id}/product/image-analysis",
        files={"file": ("product.png", b"\x89PNG\r\n\x1a\nsmall", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["data"]["image_analysis"]["status"] == "completed"


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
                    "fit_tier": "strong",
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


def test_start_simulation_run_endpoint_passes_prompt_override(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)
    captured: dict[str, object] = {}

    def fake_execute_simulation_run(**kwargs):
        captured.update(kwargs)
        return {
            "run_id": "run_prompt_001",
            "status": "completed",
            "total_requested_responses": 80,
            "total_generated_responses": 80,
            "models_used": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            "experiment_mode": "mirror",
            "survey_title": "Neo Smart Living Demo Survey",
            "question_count": 32,
            "generation_mode": "mock",
            "run_conditions": {
                "context_influence": {"enabled": True, "sources": ["audience"]},
                "generation_mode": "mock",
                "selected_models": ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"],
            },
            "personas": [],
            "response_record_preview": [],
            "response_records": [],
            "warnings": [],
            "survey_parse_warnings": [],
        }

    monkeypatch.setattr(
        "src.services.study_service.execute_simulation_run",
        fake_execute_simulation_run,
    )

    response = client.post(
        f"/api/v1/studies/{study_id}/simulation-runs",
        json={
            "prompt_user_template": "Custom run template\n\n{{persona_section}}\n\n{{survey_section}}"
        },
    )

    assert response.status_code == 200
    assert captured["prompt_user_template_override"] == (
        "Custom run template\n\n{{persona_section}}\n\n{{survey_section}}"
    )


def test_start_simulation_run_endpoint_requires_openrouter_and_saves_failed_job(client):
    study_id = _create_ready_to_run_study(client)

    response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")

    assert response.status_code == 503
    assert "OPENROUTER_API_KEY is required" in response.json()["error"]["message"]

    latest_response = client.get(f"/api/v1/studies/{study_id}/simulation-runs/latest")
    assert latest_response.status_code == 200
    latest_payload = latest_response.json()["data"]["simulation_run"]
    assert latest_payload["status"] == "failed"
    assert "OPENROUTER_API_KEY is required" in latest_payload["error"]["message"]


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
            "run_debug_summary": {
                "primary_live_path": True,
                "total_answers": 4,
                "truly_live_answers": 4,
                "fallback_answers": 0,
                "provider_error_count": 0,
                "malformed_json_count": 0,
                "ml_persona_completion_enabled": True,
            },
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
                    "question_id": "S3",
                    "question_text": "How feasible does a backyard studio feel for your property?",
                    "question_type": "likert",
                    "answer": 5,
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "S3",
                    "question_text": "How feasible does a backyard studio feel for your property?",
                    "question_type": "likert",
                    "answer": 4,
                    "segment_label": "Wellness-Oriented",
                },
                {
                    "respondent_id": "RESP_001",
                    "model": "openai/gpt-4o-mini",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q0A",
                    "question_text": "What would make you consider a modular backyard studio now?",
                    "question_type": "open_text",
                    "answer": "It feels like a realistic home office upgrade.",
                    "segment_label": "Remote Professionals",
                },
                {
                    "respondent_id": "RESP_002",
                    "model": "google/gemini-2.0-flash-001",
                    "survey_title": "Neo Smart Living Demo Survey",
                    "question_id": "Q0A",
                    "question_text": "What would make you consider a modular backyard studio now?",
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
    assert payload["filters"]["selected_question_id"] == "S3"
    assert payload["question_explorer"]["question_id"] == "S3"
    assert payload["dashboard"]["selected_model"] == "All"
    assert len(payload["dashboard"]["questions"]) >= 2
    first_question = next(
        question for question in payload["dashboard"]["questions"] if question["question_id"] == "S3"
    )
    open_text_question = next(
        question for question in payload["dashboard"]["questions"] if question["question_id"] == "Q0A"
    )
    assert first_question["question_id"] == "S3"
    assert first_question["distribution"] == [
        {"label": "Yes", "count": 0, "percentage": 0.0},
        {"label": "I'm not sure, but possibly", "count": 0, "percentage": 0.0},
        {"label": "No", "count": 0, "percentage": 0.0},
        {"label": "4", "count": 1, "percentage": 50.0},
        {"label": "5", "count": 1, "percentage": 50.0},
    ]
    assert first_question["chart_kind"] == "likert"
    assert open_text_question["question_id"] == "Q0A"
    assert open_text_question["chart_kind"] == "word_cloud"
    assert open_text_question["word_cloud_terms"]
    assert open_text_question["quotes"]
    assert payload["benchmark_snapshot"]["available"] is True
    assert payload["run_debug_summary"]["truly_live_answers"] == 4
    assert payload["realism_scorecard"]["available"] is True
    assert payload["open_text"]["available"] is True
    assert payload["records_preview"]["total"] == 4


def test_prompt_preview_endpoint_returns_first_persona_prompt(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)

    monkeypatch.setattr(
        "src.api.studies.get_prompt_preview",
        lambda *args, **kwargs: {
            "prompt_preview": {
                "persona_index": 0,
                "persona_id": "PERS_001",
                "persona_label": "Remote Professionals",
                "survey_title": "Neo Smart Living Demo Survey",
                "system_instruction": "System text",
                "user_instruction": "User text",
                "combined_prompt": "System\nSystem text\n\nUser\nUser text",
            }
        },
    )

    response = client.get(f"/api/v1/studies/{study_id}/prompt-preview")
    assert response.status_code == 200
    payload = response.json()["data"]["prompt_preview"]
    assert payload["persona_index"] == 0
    assert payload["persona_id"] == "PERS_001"
    assert "System\nSystem text" in payload["combined_prompt"]


def test_insights_endpoint_returns_executive_summary_and_charts(client, monkeypatch, test_settings):
    study_id = _create_ready_to_run_study(client)
    test_settings.openrouter_api_key = "test-openrouter-key"

    monkeypatch.setattr(
        "src.services.study_service.execute_simulation_run",
        lambda **kwargs: _mock_insights_run_payload(),
    )
    monkeypatch.setattr(
        "src.services.study_service._generate_llm_insights_summary",
        lambda **kwargs: {
            "available": True,
            "overview": "Remote-work and wellness scenarios lead the current run, but the evidence stays directional.",
            "key_findings": [
                {
                    "title": "Use case concentration",
                    "summary": "Home office and home gym surfaced as the leading intended uses.",
                    "why_it_matters": "Positioning should stay anchored in productive and wellness-oriented scenarios.",
                    "evidence_ids": ["exec_top_use_case", "use_case_1"],
                }
            ],
            "risks_and_caveats": ["Sample is synthetic and directional."],
            "recommended_next_steps": ["Test the strongest use case framing with real respondents."],
            "researcher_note": "Use this summary as a fast decision layer, not final validation.",
            "model": "openai/gpt-4o-mini",
            "from_run_id": "run_insights_001",
            "generated_at": "2026-04-15T00:00:00+00:00",
            "cached": False,
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
    assert payload["llm_summary"]["available"] is True
    assert payload["llm_summary"]["key_findings"][0]["evidence_ids"] == ["exec_top_use_case", "use_case_1"]
    assert payload["evidence_package"]["from_run_id"] == "run_insights_001"


def test_insights_endpoint_keeps_detailed_insights_when_llm_summary_unavailable(client, monkeypatch):
    study_id = _create_ready_to_run_study(client)

    monkeypatch.setattr(
        "src.services.study_service.execute_simulation_run",
        lambda **kwargs: _mock_insights_run_payload(),
    )

    start_response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert start_response.status_code == 200

    insights_response = client.get(f"/api/v1/studies/{study_id}/insights")

    assert insights_response.status_code == 200
    payload = insights_response.json()["data"]["insights"]
    assert payload["available"] is True
    assert payload["llm_summary"]["available"] is False
    assert "OPENROUTER_API_KEY" in payload["llm_summary"]["message"]
    assert payload["charts"]["barrier_ranking"]["available"] is True


def test_insights_endpoint_caches_llm_summary_per_run(client, monkeypatch, test_settings):
    study_id = _create_ready_to_run_study(client)
    test_settings.openrouter_api_key = "test-openrouter-key"
    call_count = {"value": 0}

    monkeypatch.setattr(
        "src.services.study_service.execute_simulation_run",
        lambda **kwargs: _mock_insights_run_payload(),
    )

    def _fake_generate_summary(**kwargs):
        call_count["value"] += 1
        return {
            "available": True,
            "overview": "Cached summary test.",
            "key_findings": [
                {
                    "title": "Cached finding",
                    "summary": "The first request generates the summary.",
                    "why_it_matters": "The second request should reuse the cached payload.",
                    "evidence_ids": ["finding_1"],
                }
            ],
            "risks_and_caveats": [],
            "recommended_next_steps": [],
            "researcher_note": "",
            "model": "openai/gpt-4o-mini",
            "from_run_id": "run_insights_001",
            "generated_at": "2026-04-15T00:00:00+00:00",
            "cached": False,
        }

    monkeypatch.setattr(
        "src.services.study_service._generate_llm_insights_summary",
        _fake_generate_summary,
    )

    start_response = client.post(f"/api/v1/studies/{study_id}/simulation-runs")
    assert start_response.status_code == 200

    first_response = client.get(f"/api/v1/studies/{study_id}/insights")
    second_response = client.get(f"/api/v1/studies/{study_id}/insights")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["data"]["insights"]["llm_summary"]["cached"] is False
    assert second_response.json()["data"]["insights"]["llm_summary"]["cached"] is True
    assert call_count["value"] == 1
