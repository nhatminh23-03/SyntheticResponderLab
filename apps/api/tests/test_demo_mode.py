"""Playback must work in empty studies with no model, spend, or quota availability."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
import pytest
from sqlalchemy import select, func
from src.persistence.models import Job, InterviewTurn, Study
from src.services import demo_mode


@pytest.fixture
def demo(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Demo called provider, budget, or quota code")
    for name in ["src.services.interview_service._call_openrouter_messages",
                 "src.services.usage_limits.consume_daily_quota",
                 "src.services.standalone_interview.load_interview_budget_snapshot",
                 "src.services.focus_group.load_interview_budget_snapshot"]:
        monkeypatch.setattr(name, forbidden)
    # Study creation itself uses quota; temporarily exempt only creation.
    with monkeypatch.context() as local:
        local.setattr("src.services.study_service.consume_daily_quota", lambda *a, **k: None)
        study_id = client.post("/api/v1/studies", json={}).json()["data"]["study"]["study_id"]
    client.app.state.settings.openrouter_api_key = None
    client.app.state.settings.llm_budget_usd = Decimal("0")
    return client, f"/api/v1/studies/{study_id}/interview"


def opened(demo, kind):
    client, base = demo
    response = client.post(f"{base}/demo/{kind}")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_focus_group_demo_opens(demo):
    room = opened(demo, "focus-group")["room"]
    assert room["demo"] and room["complete"]
    assert len(room["participants"]) >= 6
    assert all(p["card"] for p in room["participants"])
    assert len(room["stages_reached"]) == 5
    assert {s["kind"] for s in room["shared"]} == {"concept", "price"}
    rounds = room["rounds"]
    price = next(i for i, r in enumerate(rounds) if r.get("stimulus", {}).get("kind") == "price")
    assert any(r["stage"] == "price_reactions" for r in rounds[:price])
    assert any(r["recipients"] and r["kind"] == "probe" for r in rounds)
    assert room["session_usage"]["cost_usd"] == "0"


def test_demo_open_is_idempotent(demo):
    for kind, key, id_key in [("focus-group", "room", "room_id"), ("batch", "batch", "job_id"), ("you", "interview", "sessionId")]:
        assert opened(demo, kind)[key][id_key] == opened(demo, kind)[key][id_key]
    with ThreadPoolExecutor(4) as pool:
        copies = list(pool.map(lambda _: opened(demo, "focus-group")["room"]["room_id"], range(8)))
    assert len(set(copies)) == 1


def test_focus_group_demo_memo_and_export(demo):
    client, base = demo
    room = opened(demo, "focus-group")["room"]
    answer = room["rounds"][0]["answers"][0]
    memo = {"themes": [{"label": "Quiet space", "synthesis": "Draft", "quotes": [{"turn_id": answer["turn_id"], "text": answer["text"]}]}],
            "surprise": {"summary": "", "quote": {"turn_id": "", "text": ""}}, "answer_options": []}
    path = f"{base}/focus-group/rooms/{room['room_id']}"
    saved = client.post(path + "/manual-memo", json={"base_version": 0, "memo": memo})
    assert saved.status_code == 200, saved.text
    with ThreadPoolExecutor(4) as pool:
        copies = list(pool.map(lambda _: opened(demo, "focus-group")["room"], range(8)))
    assert all(copy["room_id"] == room["room_id"] and copy["manual_memo"]["themes"][0]["label"] == "Quiet space" for copy in copies)
    restored = opened(demo, "focus-group")["room"]
    assert restored["manual_memo"]["themes"][0]["label"] == "Quiet space"
    for format in ["markdown", "csv"]:
        response = client.post(path + "/export", json={"format": format})
        assert response.status_code == 200, response.text
        content = response.json()["data"]["export"]["content"]
        assert demo_mode.LABEL in content and "Synthetic rehearsal" in content and "Quiet space" in content
    assert client.delete(path).status_code == 200
    fresh = opened(demo, "focus-group")["room"]
    assert fresh["room_id"] != room["room_id"] and not fresh.get("manual_memo")


def test_focus_group_demo_refuses_ai(demo):
    client, base = demo
    room = opened(demo, "focus-group")["room"]
    for action, payload in [("ask", {}), ("ask", {"reveal": "concept"}), ("ask", {"reveal": "price"}),
                            ("ask", {"retry": True}), ("extend", {}), ("memo", {})]:
        response = client.post(f"{base}/focus-group/rooms/{room['room_id']}/{action}", json=payload)
        assert response.status_code == 409 and demo_mode.READ_ONLY in response.text


def test_interview_batch_demo(demo):
    client, base = demo
    batch = opened(demo, "batch")["batch"]
    assert batch["demo"] and batch["status"] == "completed" and batch["persona_count"] >= 6
    assert all(len(t["messages"]) == 16 for t in batch["transcripts"])
    assert client.get(f"{base}/batches/{batch['job_id']}").json()["data"]["batch"]["demo"]
    themes = client.get(f"{base}/batches/{batch['job_id']}/themes").json()["data"]["insights"]
    assert not themes["eligible"] and "No themes" in themes["message"]


def test_interview_batch_demo_refuses_ai(demo):
    client, base = demo
    batch = opened(demo, "batch")["batch"]
    for action in ["advance", "themes"]:
        response = client.post(f"{base}/batches/{batch['job_id']}/{action}", json={})
        assert response.status_code == 409 and demo_mode.READ_ONLY in response.text


def test_interview_you_demo(demo):
    client, base = demo
    interview = opened(demo, "you")["interview"]
    assert interview["demo"] and interview["ended"] and interview["costUsd"] == "0"
    assert len(interview["messages"]) == 16
    response = client.post(base + "/human/next-question", json={"session_id": interview["sessionId"]})
    assert response.status_code == 409 and demo_mode.READ_ONLY in response.text


def test_demo_makes_no_model_calls(demo, db_session):
    test_focus_group_demo_memo_and_export(demo)
    test_interview_batch_demo(demo)
    test_interview_you_demo(demo)
    assert db_session.scalar(select(func.count()).select_from(InterviewTurn)) == 0


def test_demo_no_key_no_login(demo):
    for kind in demo_mode.KINDS:
        opened(demo, kind)


def test_demo_isolated_per_study(demo, db_session):
    client, base = demo
    room = opened(demo, "focus-group")["room"]
    batch = opened(demo, "batch")["batch"]
    other = Study(public_id="std_other", owner_user_id="dev-local-user", lifecycle_status="active")
    db_session.add(other)
    db_session.commit()
    prefix = "/api/v1/studies/std_other/interview"
    for suffix in [f"focus-group/rooms/{room['room_id']}", f"batches/{batch['job_id']}"]:
        assert client.get(f"{prefix}/{suffix}").status_code == 404
    for action in ["manual-memo", "export", "ask"]:
        assert client.post(f"{prefix}/focus-group/rooms/{room['room_id']}/{action}", json={}).status_code == 404
    assert client.delete(f"{prefix}/focus-group/rooms/{room['room_id']}").status_code == 404


def test_missing_fixture_no_partial_copy(demo, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(demo_mode, "FIXTURES", tmp_path)
    client, base = demo
    response = client.post(base + "/demo/batch")
    assert response.status_code == 409 and "make_demo_fixtures.py" in response.text
    assert db_session.scalar(select(func.count()).select_from(Job)) == 0


def test_demo_concurrent_first_open(demo):
    with ThreadPoolExecutor(4) as pool:
        ids = list(pool.map(lambda _: opened(demo, "batch")["batch"]["job_id"], range(8)))
    assert len(set(ids)) == 1


def test_demo_foreign_device_cannot_access(demo):
    client, base = demo
    room = opened(demo, "focus-group")["room"]
    headers = {"X-Authenticated-User-Id": "classroom:another-device", "X-Authenticated-Auth-Mode": "clerk"}
    path = f"{base}/focus-group/rooms/{room['room_id']}"
    for method, suffix in [("GET", ""), ("DELETE", ""), ("POST", "/export"), ("POST", "/manual-memo")]:
        response = client.request(method, path + suffix, headers=headers, **({"json": {}} if method == "POST" else {}))
        assert response.status_code == 403
    assert client.post(base + "/demo/batch", headers=headers).status_code == 403


def test_demo_alternate_session_and_regeneration_guards(demo, db_session):
    from src.services.standalone_interview import validate_session, regenerate_answer
    from src.services.exceptions import ConflictApiError
    client, base = demo
    room = opened(demo, "focus-group")["room"]
    study = db_session.scalar(select(Study))
    with pytest.raises(ConflictApiError, match="Demo"):
        validate_session(db_session, study, room["room_id"])
    db_session.add(Job(public_id="demo_answer", study_id=study.id, job_type="interview_answer",
                       status="completed", payload_json={"demo": True}))
    db_session.commit()
    with pytest.raises(ConflictApiError, match="Demo"):
        regenerate_answer(db_session, client.app.state.settings, study, "demo_answer", {})


def test_demo_generator_ceiling_reserves_before_provider():
    from scripts.make_demo_fixtures import CappedProvider, SpendingLimit, LIMIT
    calls = []
    cap = CappedProvider(lambda **kwargs: calls.append(kwargs))
    cap.reserved = LIMIT
    with pytest.raises(SpendingLimit):
        cap(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hello"}])
    assert calls == []


def test_demo_invalid_fixture_never_inserts(demo, db_session, monkeypatch, tmp_path):
    source = json.loads((demo_mode.FIXTURES / "focus-group.json").read_text())
    source["state"]["rounds"][0]["answers"] = []
    (tmp_path / "focus-group.json").write_text(json.dumps(source))
    monkeypatch.setattr(demo_mode, "FIXTURES", tmp_path)
    client, base = demo
    response = client.post(base + "/demo/focus-group")
    assert response.status_code == 409
    assert "seed_data/demo/focus-group.json" in response.text and "make_demo_fixtures.py" in response.text
    assert "No live run was started" in response.text
    assert db_session.scalar(select(func.count()).select_from(Job)) == 0


def test_demo_preserves_existing_data_and_quota(demo, db_session):
    from copy import deepcopy
    from src.persistence.base import Base
    from src.persistence.models import StudySectionState
    study = db_session.scalar(select(Study))
    product = db_session.scalar(select(StudySectionState).where(StudySectionState.study_id == study.id, StudySectionState.section_key == "product"))
    product.value_json = {"concept": "CUSTOM CONCEPT", "photo": "private-photo.png"}
    db_session.add(Job(public_id="live_preserved", study_id=study.id, job_type="standalone_batch",
                       status="completed", payload_json={"custom": "untouched"},
                       result_json={"transcripts": [{"content": "existing live answer"}]}))
    db_session.commit()
    def snapshot():
        return {table.name: deepcopy([dict(row) for row in db_session.execute(select(table)).mappings()])
                for table in Base.metadata.sorted_tables}
    before = snapshot()
    for kind in demo_mode.KINDS:
        result = opened(demo, kind)
        assert "CUSTOM CONCEPT" not in json.dumps(result)
        assert "private-photo.png" not in json.dumps(result)
    after = snapshot()
    for table, rows in before.items():
        if table == Job.__tablename__:
            assert all(row in after[table] for row in rows)
            assert len(after[table]) == len(rows) + 3
        else:
            assert after[table] == rows, f"Demo changed {table} (including quota/usage/configuration)"


def test_demo_saved_themes_are_grounded(demo, monkeypatch, tmp_path):
    from copy import deepcopy
    fixture = demo_mode.load_fixture("batch")
    transcripts = fixture["state"]["transcripts"]
    quote = transcripts[0]["messages"][1]["content"]
    pid = transcripts[0]["persona_id"]
    words = quote.split()
    memo = {"themes": [{"label": f"Theme {i}", "synthesis": "Example synthesis", "sentiment": "neutral",
                         "count": 1, "representative_quote": quote, "quote_persona_id": pid} for i in range(3)],
            "surprise": {"summary": "Example surprise", "quote": quote, "quote_persona_id": pid},
            "answer_options": [{"text": " ".join(words[i:i+8]), "quote_persona_id": pid} for i in range(3)]}
    fixture["state"]["insights"] = memo
    (tmp_path / "batch.json").write_text(json.dumps(fixture))
    monkeypatch.setattr(demo_mode, "FIXTURES", tmp_path)
    batch = opened(demo, "batch")["batch"]
    client, base = demo
    view = client.get(f"{base}/batches/{batch['job_id']}/themes").json()["data"]["insights"]
    assert view["available"] and not view["eligible"] and view["saved"] == memo
    invalid = deepcopy(fixture)
    invalid["state"]["insights"]["themes"][0]["representative_quote"] = "A fabricated citation"
    (tmp_path / "batch.json").write_text(json.dumps(invalid))
    from src.services.exceptions import ConflictApiError
    with pytest.raises(ConflictApiError, match="batch.json"):
        demo_mode.load_fixture("batch")


def test_demo_history_retains_flags_and_read_only(demo):
    client, base = demo
    room = opened(demo, "focus-group")["room"]
    restored = client.get(f"{base}/focus-group/rooms/{room['room_id']}").json()["data"]["room"]
    assert restored["demo"] and restored["demo_label"] == demo_mode.LABEL
    assert restored["rounds"] == room["rounds"]
    test_focus_group_demo_refuses_ai(demo)
    test_interview_batch_demo(demo)


def test_demo_generator_conservative_reservation_on_failure():
    from scripts.make_demo_fixtures import CappedProvider, SpendingLimit, LIMIT
    calls = []
    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("uncertain provider result")
    cap = CappedProvider(fail)
    with pytest.raises(RuntimeError):
        cap(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hello"}])
    assert cap.reserved > 0 and calls[0]["max_tokens"] == 512 and calls[0]["max_attempts"] == 1
    cap.reserved = LIMIT
    with pytest.raises(SpendingLimit):
        cap(model="openai/gpt-4o-mini", messages=[])
    assert len(calls) == 1


def test_demo_generator_drives_services_in_isolated_database(monkeypatch, tmp_path):
    from scripts import make_demo_fixtures as generator
    calls = {}
    for module, name in [(generator.fg, "start_room"), (generator.fg, "ask_round"),
                         (generator.si, "start_batch"), (generator.si, "advance_batch"),
                         (generator.si, "next_human_question")]:
        original = getattr(module, name)
        def counted(*args, _name=name, _original=original, **kwargs):
            calls[_name] = calls.get(_name, 0) + 1
            return _original(*args, **kwargs)
        monkeypatch.setattr(module, name, counted)
    monkeypatch.setattr(generator, "OUTPUT", tmp_path)
    generator.build(provisional=True)
    monkeypatch.setattr(demo_mode, "FIXTURES", tmp_path)
    for kind in demo_mode.KINDS:
        fixture = demo_mode.load_fixture(kind)
        assert fixture["provisional"] and fixture["generation"]["limit_usd"] == "2"
    assert calls == {"start_room": 1, "ask_round": 7, "start_batch": 1,
                     "advance_batch": 96, "next_human_question": 8}


def test_demo_alternate_http_endpoints_refuse_before_budget(demo, db_session, monkeypatch):
    from src.persistence.models import Persona
    from src.persistence.persona_seed import load_persona_seed_rows
    from src.services import interview_service
    def forbidden(*args, **kwargs):
        pytest.fail("Alternate demo route reached budget code")
    monkeypatch.setattr(interview_service, "load_interview_budget_snapshot", forbidden)
    row = load_persona_seed_rows()[0]
    if db_session.get(Persona, row["persona_id"]) is None:
        db_session.add(Persona(**row))
        db_session.commit()
    client, base = demo
    for kind, key, id_key in [("focus-group", "room", "room_id"), ("batch", "batch", "job_id"), ("you", "interview", "sessionId")]:
        session_id = opened(demo, kind)[key][id_key]
        for endpoint, payload in [
            ("chat", {"standalone": True, "prompt": "What matters?", "model": "openai/gpt-4o-mini"}),
            ("chat", {"standalone": False, "prompt": "What matters?"}),
            ("interviewer/next-question", {}),
            ("compare", {"question": "What matters?", "model_ids": ["openai/gpt-4o-mini", "google/gemini-2.5-flash-lite"]}),
        ]:
            response = client.post(f"{base}/{endpoint}", json={**payload, "persona_id": row["persona_id"], "session_id": session_id})
            assert response.status_code == 409 and demo_mode.READ_ONLY in response.text, response.text
