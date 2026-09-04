from __future__ import annotations

from decimal import Decimal

import pytest

from src.services.interviewer_agent import (
    DEFAULT_INTERVIEW_TURN_LIMIT,
    build_interviewer_messages,
    derive_interviewer_turn_plan,
    normalize_interviewer_question,
    sanitize_interview_transcript,
)


BRIEF = {
    "primary_question": "Why do homeowners accept or reject a backyard workspace?",
    "hypotheses": ["Installation confidence may matter."],
    "decisions_to_inform": ["Which concern should launch messaging address?"],
    "focus_fit_tiers": ["strong"],
    "focus_segments": ["Remote professionals"],
    "known_context": "The concept is a compact backyard workspace.",
    "notes": "",
}


def test_turn_plan_uses_whole_interview_estimate_for_models_and_persona_count():
    default_plan = derive_interviewer_turn_plan()
    larger_batch = derive_interviewer_turn_plan(
        persona_count=30,
    )

    assert DEFAULT_INTERVIEW_TURN_LIMIT == 8
    assert default_plan.estimated_cost_per_turn_usd == Decimal("0.00135")
    assert default_plan.turn_limit == DEFAULT_INTERVIEW_TURN_LIMIT
    assert default_plan.estimated_run_cost_usd == Decimal("0.01080")
    assert larger_batch.estimated_cost_per_turn_usd == Decimal("0.01350")
    assert larger_batch.estimated_run_cost_usd == Decimal("0.10800")
    assert larger_batch.turn_limit == DEFAULT_INTERVIEW_TURN_LIMIT


def test_turn_plan_reports_over_budget_estimate_and_rejects_invalid_inputs():
    too_expensive = derive_interviewer_turn_plan(
        persona_count=30,
        interviewer_model="anthropic/claude-sonnet-4.5",
        interviewee_model="anthropic/claude-sonnet-4.5",
    )

    assert too_expensive.estimated_cost_per_turn_usd == Decimal("0.45000")
    assert too_expensive.estimated_run_cost_usd == Decimal("3.60000")
    assert too_expensive.turn_limit == DEFAULT_INTERVIEW_TURN_LIMIT
    with pytest.raises(ValueError, match="between 3 and 30"):
        derive_interviewer_turn_plan(persona_count=2)
    with pytest.raises(ValueError, match="curated catalog"):
        derive_interviewer_turn_plan(
            interviewer_model="provider/not-curated",
        )


def test_followup_prompt_uses_latest_answer_and_never_exposes_fit_tier():
    transcript = [
        {"role": "user", "content": "What concerns you about the concept?"},
        {
            "role": "assistant",
            "content": "I would worry about weeks of noisy installation.",
        },
    ]

    messages = build_interviewer_messages(
        research_brief=BRIEF,
        transcript=transcript,
        turn_number=2,
        turn_limit=8,
    )

    assert messages[0]["role"] == "system"
    assert "Do not replay a fixed questionnaire" in messages[0]["content"]
    assert "MUST follow up on a concrete detail" in messages[0]["content"]
    assert "weeks of noisy installation" in messages[1]["content"]
    assert "TURN 2 OF 8" in messages[1]["content"]
    assert "focus_fit_tiers" not in messages[1]["content"]
    assert "strong" not in messages[1]["content"]
    assert "fit_tier" not in str(messages)


def test_opening_prompt_comes_from_brief_without_a_fixed_question():
    messages = build_interviewer_messages(
        research_brief=BRIEF,
        transcript=[],
        turn_number=1,
        turn_limit=4,
    )

    assert BRIEF["primary_question"] in messages[1]["content"]
    assert "No questions have been asked yet" in messages[1]["content"]
    assert "derive the first question from the research brief" in messages[1]["content"].lower()


def test_interviewer_endpoint_generates_and_persists_answer_derived_questions(
    client,
    monkeypatch,
):
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    saved = client.patch(
        f"/api/v1/studies/{study_id}/interview/brief",
        json=BRIEF,
    )
    assert saved.status_code == 200

    client.app.state.settings.openrouter_api_key = "test-key"
    provider_outputs = iter(
        [
            "What feels most important when you imagine adding a backyard workspace?",
            "You mentioned permit uncertainty; what would make that process feel manageable?",
        ]
    )
    captured_messages = []

    def fake_call_openrouter_messages(**kwargs):
        from src.services.interview_cache import InterviewAnswer

        captured_messages.append(kwargs["messages"])
        return InterviewAnswer(
            text=next(provider_outputs),
            model=kwargs["model"],
            tokens_in=120,
            tokens_out=14,
            cost_usd=Decimal("0.0002"),
        )

    monkeypatch.setattr(
        "src.services.interview_service._call_openrouter_messages",
        fake_call_openrouter_messages,
    )

    first = client.post(
        f"/api/v1/studies/{study_id}/interview/interviewer/next-question",
        json={"persona_id": "neo-001"},
    )

    assert first.status_code == 200
    first_payload = first.json()["data"]["interviewer_question"]
    assert first_payload["question"].startswith("What feels most important")
    assert first_payload["complete"] is False
    assert first_payload["turn_number"] == 1
    assert first_payload["turn_limit"] == DEFAULT_INTERVIEW_TURN_LIMIT
    assert first_payload["session_usage"] == {
        "tokens_in": 120,
        "tokens_out": 14,
        "cost_usd": "0.0002",
    }
    assert BRIEF["primary_question"] in captured_messages[0][1]["content"]
    assert "focus_fit_tiers" not in captured_messages[0][1]["content"]

    prior_answer = "The biggest issue is not knowing whether permits will take months."
    followup = client.post(
        f"/api/v1/studies/{study_id}/interview/interviewer/next-question",
        json={
            "persona_id": "neo-001",
            "session_id": first_payload["session_id"],
            "messages": [
                {"role": "user", "content": first_payload["question"]},
                {"role": "assistant", "content": prior_answer},
            ],
        },
    )

    assert followup.status_code == 200
    followup_payload = followup.json()["data"]["interviewer_question"]
    assert followup_payload["question"].startswith("You mentioned permit uncertainty")
    assert followup_payload["turn_number"] == 2
    assert followup_payload["session_id"] == first_payload["session_id"]
    assert prior_answer in captured_messages[1][1]["content"]
    assert followup_payload["session_usage"] == {
        "tokens_in": 240,
        "tokens_out": 28,
        "cost_usd": "0.0004",
    }

    with client.app.state.session_factory() as session:
        from sqlalchemy import select

        from src.persistence.models import InterviewTurn

        persisted = session.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == first_payload["session_id"])
            .order_by(InterviewTurn.created_at, InterviewTurn.id)
        ).all()
    assert [turn.role for turn in persisted] == ["user", "user"]
    assert [turn.text for turn in persisted] == [
        first_payload["question"],
        followup_payload["question"],
    ]
    assert all(turn.model == "google/gemini-2.5-flash-lite" for turn in persisted)


def test_interviewer_endpoint_requires_brief_and_rejects_over_budget_run(
    client,
    monkeypatch,
):
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    missing_brief = client.post(
        f"/api/v1/studies/{study_id}/interview/interviewer/next-question",
        json={"persona_id": "neo-001"},
    )
    assert missing_brief.status_code == 409
    assert "Save a research brief" in missing_brief.json()["error"]["message"]

    saved = client.patch(
        f"/api/v1/studies/{study_id}/interview/brief",
        json=BRIEF,
    )
    assert saved.status_code == 200
    monkeypatch.setattr(
        "src.services.interview_service._call_openrouter_messages",
        lambda **kwargs: pytest.fail("An over-budget run must not call the provider."),
    )

    stopped = client.post(
        f"/api/v1/studies/{study_id}/interview/interviewer/next-question",
        json={
            "persona_id": "neo-001",
            "persona_count": 30,
            "interviewer_model": "anthropic/claude-sonnet-4.5",
            "interviewee_model": "anthropic/claude-sonnet-4.5",
        },
    )

    assert stopped.status_code == 429
    assert stopped.json()["error"]["details"] == {
        "scope": "run",
        "projected_cost_usd": "3.60",
        "budget_usd": "0.75",
        "estimated_cost_usd": "3.60",
    }


def test_interviewer_endpoint_stops_at_the_fixed_turn_limit(client, monkeypatch):
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    client.patch(f"/api/v1/studies/{study_id}/interview/brief", json=BRIEF)
    monkeypatch.setattr(
        "src.services.interview_service._call_openrouter_messages",
        lambda **kwargs: pytest.fail("A completed turn plan must not call the provider."),
    )

    response = client.post(
        f"/api/v1/studies/{study_id}/interview/interviewer/next-question",
        json={
            "persona_id": "neo-001",
            "messages": [
                message
                for turn in range(DEFAULT_INTERVIEW_TURN_LIMIT)
                for message in (
                    {"role": "user", "content": f"Question {turn + 1}?"},
                    {"role": "assistant", "content": f"Answer {turn + 1}."},
                )
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]["interviewer_question"]
    assert payload["turn_limit"] == DEFAULT_INTERVIEW_TURN_LIMIT
    assert payload["turn_number"] == DEFAULT_INTERVIEW_TURN_LIMIT
    assert payload["complete"] is True
    assert payload["question"] is None


def test_interviewer_endpoint_rechecks_preflight_when_models_change(client, monkeypatch):
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    client.patch(f"/api/v1/studies/{study_id}/interview/brief", json=BRIEF)
    client.app.state.settings.openrouter_api_key = "test-key"

    from src.services.interview_cache import InterviewAnswer

    provider_calls = 0

    def fake_call_openrouter_messages(**kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return InterviewAnswer(
            text="What matters most about the workspace?",
            model=kwargs["model"],
            tokens_in=100,
            tokens_out=10,
            cost_usd=Decimal("0.0002"),
        )

    monkeypatch.setattr(
        "src.services.interview_service._call_openrouter_messages",
        fake_call_openrouter_messages,
    )
    first = client.post(
        f"/api/v1/studies/{study_id}/interview/interviewer/next-question",
        json={"persona_id": "neo-001"},
    )
    first_payload = first.json()["data"]["interviewer_question"]

    changed_to_over_budget = client.post(
        f"/api/v1/studies/{study_id}/interview/interviewer/next-question",
        json={
            "persona_id": "neo-001",
            "session_id": first_payload["session_id"],
            "persona_count": 30,
            "interviewer_model": "anthropic/claude-sonnet-4.5",
            "interviewee_model": "anthropic/claude-sonnet-4.5",
            "messages": [
                {"role": "user", "content": first_payload["question"]},
                {"role": "assistant", "content": "Quiet installation matters most."},
            ],
        },
    )

    assert first.status_code == 200
    assert changed_to_over_budget.status_code == 429
    assert changed_to_over_budget.json()["error"]["details"]["estimated_cost_usd"] == "3.60"
    assert provider_calls == 1


def test_interviewer_endpoint_rejects_an_unanswered_transcript(client):
    study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    client.patch(f"/api/v1/studies/{study_id}/interview/brief", json=BRIEF)

    response = client.post(
        f"/api/v1/studies/{study_id}/interview/interviewer/next-question",
        json={
            "persona_id": "neo-001",
            "messages": [{"role": "user", "content": "What matters most?"}],
        },
    )

    assert response.status_code == 400
    assert "must answer" in response.json()["error"]["message"]


@pytest.mark.parametrize(
    "messages, error",
    [
        ([{"role": "assistant", "content": "An answer without a question."}], "alternate"),
        ([{"role": "user", "content": "An unanswered question?"}], "must answer"),
        ([{"role": "user", "content": ""}], "non-empty"),
    ],
)
def test_transcript_must_be_complete_and_alternating(messages, error):
    with pytest.raises(ValueError, match=error):
        sanitize_interview_transcript(messages)


def test_question_normalization_uses_one_question_and_rejects_empty_output():
    assert normalize_interviewer_question("Question: Why did permits stand out") == (
        "Why did permits stand out?"
    )
    assert normalize_interviewer_question("Why permits?\nWhat else?") == "Why permits?"
    with pytest.raises(RuntimeError, match="empty question"):
        normalize_interviewer_question(" \n ")
