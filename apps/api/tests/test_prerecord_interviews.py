from __future__ import annotations

import sys
from decimal import Decimal

import pytest
from sqlalchemy import select

from conftest import API_ROOT
from src.persistence.models import InterviewCacheEntry, InterviewTurn, Persona, Study
from src.persistence.persona_seed import load_persona_seed_rows
from src.services import interview_service
from src.services.exceptions import TransientProviderError
from src.services.interview_cache import InterviewAnswer

REPO_ROOT = API_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import prerecord_interviews as runner  # noqa: E402


@pytest.fixture
def recording(db_session, test_settings, monkeypatch):
    for row in load_persona_seed_rows()[:3]:
        db_session.add(Persona(**row))
    db_session.commit()
    settings = test_settings.model_copy(update={"openrouter_api_key": "stub-key", "cache_mode": "off"})

    def forbidden(**kwargs):
        pytest.fail("Unexpected provider call")

    monkeypatch.setattr(interview_service, "_call_openrouter_messages", forbidden)
    return settings


def test_complete_adaptive_recordings_measured_usage_and_free_replay(
    db_session, recording, monkeypatch, capsys,
):
    calls = []

    def provider(**kwargs):
        messages = kwargs["messages"]
        is_interviewer = "You are the interviewer" in messages[0]["content"]
        if is_interviewer:
            prompt = messages[-1]["content"]
            if "TURN 1 OF 8" not in prompt:
                assert "A synthetic answer about installation" in prompt
            text = f"What about installation at turn {len(calls)}?"
        else:
            assert messages[-1]["role"] == "user"
            assert "What about installation" in messages[-1]["content"]
            text = "A synthetic answer about installation."
        assert "fit_tier" not in str(messages)
        calls.append(kwargs)
        return InterviewAnswer(text=text, model=kwargs["model"], tokens_in=123,
                               tokens_out=45, cost_usd=Decimal("0.000123"))

    monkeypatch.setattr(interview_service, "_call_openrouter_messages", provider)
    args = runner.build_parser().parse_args([])
    assert args.models == list(runner.DEFAULT_MODELS)
    assert runner.run(args, recording) == 0
    assert len(calls) == 2 * 3 * 8 * 2
    turns = db_session.scalars(select(InterviewTurn)).all()
    paid = [turn for turn in turns if turn.cost_usd > 0]
    assert len(paid) == len(calls)
    assert all(turn.tokens_in == 123 and turn.tokens_out == 45 for turn in paid)
    assert sum(turn.cost_usd for turn in turns) == Decimal("0.011808")
    assert len(db_session.scalars(select(InterviewCacheEntry)).all()) == len(calls)
    for model in args.models:
        assert len([t for t in turns if t.model == model and t.role == "assistant"]) == 24
    output = capsys.readouterr().out
    assert output.count("turns=24, tokens_in=5904, tokens_out=2160, measured_usd=$0.005904") == 2

    def forbidden(**kwargs):
        pytest.fail("Replay must not call a provider")

    monkeypatch.setattr(interview_service, "_call_openrouter_messages", forbidden)
    assert runner.run(args, recording.model_copy(update={"openrouter_api_key": "", "cache_mode": "replay_only"})) == 0
    assert capsys.readouterr().out.count("turns=24, tokens_in=0, tokens_out=0, measured_usd=$0.000000") == 2
    assert sum(t.cost_usd for t in db_session.scalars(select(InterviewTurn)).all()) == Decimal("0.011808")


@pytest.mark.parametrize("flags,code", [(["--dry-run"], 0), (["--dry-run", "--max-usd", "0"], 2)])
def test_dry_run_and_projection_refusal_do_not_write(db_session, recording, capsys, flags, code):
    assert runner.run(runner.build_parser().parse_args(flags), recording) == code
    output = capsys.readouterr().out
    # Two sides per persona, each with the catalog's 10k input / 2k output allowance.
    expected = 3 * 2 * ((Decimal("1.0353") * 10000 + Decimal("2.0706") * 2000)
                       + (Decimal("0.32") * 10000 + Decimal("1.28") * 2000)) / 1000000
    assert f"Projected cost: ${expected:.6f}" in output
    assert db_session.scalars(select(Study)).all() == []
    assert db_session.scalars(select(InterviewCacheEntry)).all() == []


@pytest.mark.parametrize("budget", ["0", "0.01"])
def test_run_caps_refuse_before_calls(db_session, recording, budget):
    assert runner.run(runner.build_parser().parse_args([]), recording.model_copy(
        update={"llm_budget_usd": Decimal(budget)})) == 2
    assert db_session.scalars(select(Study)).all() == []


def test_class_cap_refuses_before_calls(db_session, recording):
    study = Study(public_id="std_spent", lifecycle_status="draft")
    db_session.add(study)
    db_session.flush()
    db_session.add(InterviewTurn(study_id=study.id, persona_id="prior", session_id="prior",
                                 role="assistant", text="prior", model="prior", tokens_in=1,
                                 tokens_out=1, cost_usd=Decimal("22.49")))
    db_session.commit()
    assert runner.run(runner.build_parser().parse_args([]), recording) == 2


@pytest.mark.parametrize("cost,max_usd,budget", [("0.2", "0.15", "0.75"), ("0.8", "2", "0.75"),
                                                  ("0.149", "0.15", "0.75")])
def test_measured_overruns_save_paid_turn_and_stop(
    db_session, recording, monkeypatch, capsys, cost, max_usd, budget,
):
    calls = []

    def provider(**kwargs):
        calls.append(kwargs)
        return InterviewAnswer(text="What matters?", model=kwargs["model"], tokens_in=123,
                               tokens_out=45, cost_usd=Decimal(cost))

    monkeypatch.setattr(interview_service, "_call_openrouter_messages", provider)
    args = runner.build_parser().parse_args(["--max-usd", max_usd])
    assert runner.run(args, recording.model_copy(update={"llm_budget_usd": Decimal(budget)})) == 2
    assert len(calls) == 1
    assert len(db_session.scalars(select(InterviewCacheEntry)).all()) == 1
    turns = db_session.scalars(select(InterviewTurn)).all()
    assert len(turns) == 1
    assert turns[0].cost_usd.quantize(Decimal("0.000001")) == Decimal(cost)
    assert f"measured_usd=${Decimal(cost):.6f}" in capsys.readouterr().out


def test_missing_personas_and_missing_key(db_session, recording):
    assert runner.run(runner.build_parser().parse_args(["--personas", "4"]), recording) == 2
    assert runner.run(runner.build_parser().parse_args([]), recording.model_copy(
        update={"openrouter_api_key": ""})) == 2
    assert db_session.scalars(select(InterviewTurn)).all() == []


@pytest.mark.parametrize("flags", [["--personas", "2"], ["--personas", "31"],
                                   ["--models", "unknown"], ["--max-usd", "NaN"]])
def test_invalid_cli_arguments(flags):
    with pytest.raises(SystemExit):
        runner.build_parser().parse_args(flags)


def test_model_override_and_duplicate_selection(db_session, recording, capsys):
    model = "qwen/qwen3.7-plus"
    args = runner.build_parser().parse_args(["--models", model, model, "--dry-run"])
    assert runner.run(args, recording) == 0
    assert capsys.readouterr().out.count("personas=3, turns/persona=8") == 1


def test_answer_overrun_is_cached_before_batch_stops(db_session, recording, monkeypatch):
    calls = []

    def provider(**kwargs):
        calls.append(kwargs)
        return InterviewAnswer(text="What matters?", model=kwargs["model"], tokens_in=12,
                               tokens_out=4, cost_usd=Decimal("0.001" if len(calls) == 1 else "0.2"))

    monkeypatch.setattr(interview_service, "_call_openrouter_messages", provider)
    assert runner.run(runner.build_parser().parse_args(["--max-usd", "0.15"]), recording) == 2
    assert len(calls) == 2
    assert len(db_session.scalars(select(InterviewCacheEntry)).all()) == 2
    assert len(db_session.scalars(select(InterviewTurn).where(InterviewTurn.role == "assistant")).all()) == 1


def test_cli_entrypoint_dry_run(recording):
    import os
    import subprocess

    env = os.environ.copy()
    env["DATABASE_URL"] = recording.database_url
    env["OPENROUTER_API_KEY"] = ""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/prerecord_interviews.py"), "--dry-run"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "no provider calls or database writes were made" in result.stdout


def test_replay_only_cold_cache_never_calls_provider(db_session, recording):
    assert runner.run(runner.build_parser().parse_args([]), recording.model_copy(
        update={"cache_mode": "replay_only"})) == 2
    assert db_session.scalars(select(InterviewCacheEntry)).all() == []


def test_free_replay_with_zero_spend_allowance(db_session, recording, monkeypatch):
    def provider(**kwargs):
        return InterviewAnswer(text="What matters?", model=kwargs["model"], tokens_in=12,
                               tokens_out=4, cost_usd=Decimal("0.0001"))

    monkeypatch.setattr(interview_service, "_call_openrouter_messages", provider)
    assert runner.run(runner.build_parser().parse_args([]), recording) == 0
    paid_before = sum(t.cost_usd for t in db_session.scalars(select(InterviewTurn)).all())

    def forbidden(**kwargs):
        pytest.fail("Free replay must not call a provider")

    monkeypatch.setattr(interview_service, "_call_openrouter_messages", forbidden)
    args = runner.build_parser().parse_args(["--max-usd", "0"])
    replay_settings = recording.model_copy(update={
        "cache_mode": "replay_only", "openrouter_api_key": "", "llm_budget_usd": Decimal("0"),
    })
    assert runner.run(args, replay_settings) == 0
    turns = db_session.scalars(select(InterviewTurn)).all()
    assert sum(t.role == "assistant" for t in turns) == 96
    assert sum(t.cost_usd for t in turns) == paid_before


def test_transient_provider_fault_is_retried_then_abandons_only_that_persona(
    db_session, recording, monkeypatch, capsys,
):
    """A hiccup must not discard the batch, and a retry must not be infinite.

    One model, 3 personas, 8 turns, 2 calls per turn = 16 calls per persona.
    Call 1 fails once and the retry succeeds, so P001 completes in 17 calls.
    Calls 18 and 19 are P002's first question and its one retry, both failing, so
    P002 is abandoned. P003 must still be recorded — before this fix, a single
    empty completion ended every remaining call in the run.
    """
    calls = {"n": 0}
    FAIL_ON = {1, 18, 19}

    def provider(**kwargs):
        calls["n"] += 1
        if calls["n"] in FAIL_ON:
            raise TransientProviderError("OpenRouter chat response included empty assistant text.")
        return InterviewAnswer(text="A synthetic answer about installation.", model=kwargs["model"],
                               tokens_in=123, tokens_out=45, cost_usd=Decimal("0.000123"))

    monkeypatch.setattr(interview_service, "_call_openrouter_messages", provider)
    code = runner.run(runner.build_parser().parse_args(["--models", "qwen/qwen3.7-plus"]), recording)

    # Exit 3, not 0: a partial batch must never read as success.
    assert code == 3
    err = capsys.readouterr().err
    assert "abandoned qwen/qwen3.7-plus / P002" in err
    assert "abandoned qwen/qwen3.7-plus / P001" not in err
    assert "abandoned qwen/qwen3.7-plus / P003" not in err
    # Retried once each, never spun on: exactly two retry attempts across the run,
    # one for the call that recovered and one for the call that did not. Asserting the
    # retry count rather than a total call count keeps this failing if the retry ever
    # becomes a loop, without pinning the arithmetic of a turn plan that may change.
    assert err.count("retrying after:") == 2

    # P002's abandoned transcript is short, not absent: whatever turns were already
    # recorded were paid for, so they stay in the ledger. P001 and P003 are complete.
    counts: dict[str, int] = {}
    for turn in db_session.scalars(select(InterviewTurn)).all():
        counts[turn.persona_id] = counts.get(turn.persona_id, 0) + 1
    assert counts["P001"] == counts["P003"] > 0
    assert 0 < counts["P002"] < counts["P001"]
