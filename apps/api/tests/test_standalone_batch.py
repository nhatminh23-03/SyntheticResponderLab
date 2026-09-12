from decimal import Decimal
from uuid import UUID, uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, func

from src.persistence.models import Persona, Study, StudySectionState, PersonaPreviewRun, InterviewTurn, Job
from src.persistence.persona_seed import load_persona_seed_rows
from src.services.interview_cache import InterviewAnswer
from src.services.interview_service import _call_openrouter_messages as real_provider

MODEL = "openai/gpt-4o-mini"


@pytest.fixture
def classroom(client, db_session, monkeypatch):
    db_session.add_all(Persona(**row) for row in load_persona_seed_rows())
    db_session.commit()
    study_id = client.post('/api/v1/studies', json={}).json()['data']['study']['study_id']
    client.app.state.settings.openrouter_api_key = 'stub'
    calls = []
    def provider(**kw):
        calls.append(kw)
        is_question = 'You are the interviewer' in kw['messages'][0]['content']
        return InterviewAnswer(text=f'Why does detail {len(calls)} matter?' if is_question else f'I am interested in option {len(calls)}.',
                               model=kw['model'], tokens_in=10, tokens_out=5, cost_usd=Decimal('.001'))
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', provider)
    return client, study_id, calls


def start(client, study_id, **overrides):
    return client.post(f'/api/v1/studies/{study_id}/interview/batches', json={
        'request_id': str(uuid4()), 'persona_count': 3, 'interviewer_model': MODEL,
        'interviewee_model': MODEL, **overrides})


def step(client, study_id, batch, **extra):
    return client.post(f'/api/v1/studies/{study_id}/interview/batches/{batch["job_id"]}/advance',
                       json={'revision': batch['revision'], **extra})


def finish(client, study_id, batch):
    while batch['status'] == 'running':
        response = step(client, study_id, batch)
        assert response.status_code == 200, response.text
        batch = response.json()['data']['batch']
    return batch


def test_batch_without_preview_or_sections_complete_adaptive_isolated_and_free_replay(classroom, db_session):
    client, study_id, calls = classroom
    study = db_session.scalar(select(Study).where(Study.public_id == study_id))
    # Remove even bootstrap sections: the batch must not require or recreate them.
    for section in db_session.scalars(select(StudySectionState).where(StudySectionState.study_id == study.id)):
        db_session.delete(section)
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(PersonaPreviewRun)) == 0
    batch = finish(client, study_id, start(client, study_id).json()['data']['batch'])
    assert batch['status'] == 'completed'
    assert batch['completed_personas'] == 3
    assert len(calls) == 48
    assert Decimal(batch['session_usage']['cost_usd']) == Decimal('.048')
    assert Decimal(batch['estimated_cost_usd']) > 0
    for i, transcript in enumerate(batch['transcripts']):
        assert len(transcript['messages']) == 16
        opening = calls[i * 16]['messages'][-1]['content']
        assert 'No questions have been asked yet' in opening
        followup = calls[i * 16 + 2]['messages'][-1]['content']
        assert transcript['messages'][1]['content'] in followup
    replay = finish(client, study_id, start(client, study_id).json()['data']['batch'])
    assert len(calls) == 48
    assert replay['transcripts'] == batch['transcripts']
    assert Decimal(replay['session_usage']['cost_usd']) == 0
    assert db_session.scalar(select(func.count()).select_from(StudySectionState).where(StudySectionState.study_id == study.id)) == 0
    assert client.get(f'/api/v1/studies/{study_id}/interview/runs/latest').json()['data']['interview_run'] is None


@pytest.mark.parametrize('change', [
    {'persona_count': 2}, {'persona_count': 31}, {'persona_count': True}, {'persona_count': '3'},
    {'interviewer_model': 'missing'}, {'interviewee_model': 'missing'},
    {'interviewer_model': 'anthropic/claude-sonnet-4.5'},
    {'interviewer_model': 'anthropic/claude-sonnet-4.5', 'allow_expensive_models': 'yes'},
])
def test_batch_validation_before_paid_call(classroom, change):
    client, study_id, calls = classroom
    assert start(client, study_id, **change).status_code == 400
    assert calls == []


def test_batch_unavailable_personas_rejected(classroom, db_session):
    client, study_id, calls = classroom
    for persona in db_session.scalars(select(Persona)).all()[2:]:
        db_session.delete(persona)
    db_session.commit()
    assert start(client, study_id).status_code == 400
    assert calls == []


def test_batch_quota_stop_preserves_transcript_and_every_incurred_call(classroom):
    client, study_id, calls = classroom
    client.app.state.settings.llm_budget_usd = Decimal('.0175')
    batch = start(client, study_id).json()['data']['batch']
    while True:
        response = step(client, study_id, batch)
        if response.status_code == 429:
            break
        assert response.status_code == 200, response.text
        batch = response.json()['data']['batch']
    error = response.json()['error']
    assert error['code'] == 'quota_exceeded'
    assert error['details']['scope'] == 'run'
    stopped = error['details']['batch']
    assert stopped['status'] == 'budget_stopped'
    assert stopped['completed_personas'] == 1
    assert len(stopped['transcripts'][0]['messages']) == 16
    assert Decimal(stopped['session_usage']['cost_usd']) == Decimal('.018')
    assert len(calls) == 18
    assert step(client, study_id, stopped).json()['data']['batch'] == stopped


def test_batch_failure_status_resume_and_duplicate_submissions(classroom, monkeypatch):
    client, study_id, calls = classroom
    request_id = str(uuid4())
    batch = start(client, study_id, request_id=request_id).json()['data']['batch']
    assert start(client, study_id, request_id=request_id).json()['data']['batch']['job_id'] == batch['job_id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: step(client, study_id, batch), range(2)))
    assert all(r.status_code == 200 for r in results)
    assert len(calls) == 1
    batch = results[0].json()['data']['batch']
    original = __import__('src.services.interview_service', fromlist=['x'])._call_openrouter_messages
    def fail(**kw):
        raise RuntimeError('Temporary provider failure; response not received')
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', fail)
    failed = step(client, study_id, batch).json()['data']['batch']
    assert failed['status'] == 'failed'
    assert failed['error']['persona_id'] == failed['persona_ids'][0]
    assert failed['error']['model'] == MODEL
    assert failed['error']['revision'] == 2
    assert Decimal(failed['session_usage']['cost_usd']) == Decimal('.001')
    retrieved = client.get(f'/api/v1/studies/{study_id}/interview/batches/{batch["job_id"]}').json()['data']['batch']
    assert retrieved == failed
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', original)
    resumed = finish(client, study_id, step(client, study_id, failed, retry=True).json()['data']['batch'])
    assert resumed['status'] == 'completed'
    assert len(calls) == 48



@pytest.mark.parametrize("cost", [Decimal(".001"), Decimal("1")])
def test_rejected_question_records_cost_and_recovers(classroom, db_session, monkeypatch, cost):
    client, study_id, calls = classroom
    valid_provider = __import__('src.services.interview_service', fromlist=['x'])._call_openrouter_messages

    def rejected(**kw):
        calls.append(kw)
        return InterviewAnswer(text="Question:", model=kw["model"], tokens_in=10,
                               tokens_out=5, cost_usd=cost)

    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', rejected)
    batch = start(client, study_id).json()['data']['batch']
    response = step(client, study_id, batch)
    if cost == Decimal("1"):
        assert response.status_code == 429
        error = response.json()['error']
        assert error['code'] == 'quota_exceeded'
        failed = error['details']['batch']
        assert failed['status'] == 'budget_stopped'
    else:
        assert response.status_code == 200
        failed = response.json()['data']['batch']
        assert failed['status'] == 'failed'
    assert Decimal(failed['session_usage']['cost_usd']) == cost
    db_session.expire_all()
    assert db_session.scalar(select(func.sum(InterviewTurn.cost_usd)).where(
        InterviewTurn.session_id == batch['job_id'])) == cost
    assert failed['transcripts'][0]['messages'] == []
    assert len(calls) == 1
    # A duplicate or non-explicit retry cannot authorize another paid attempt.
    assert step(client, study_id, failed).json()['data']['batch'] == failed
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', valid_provider)
    retried = step(client, study_id, failed, retry=True).json()['data']['batch']
    if cost == Decimal("1"):
        assert retried == failed
        assert len(calls) == 1
    else:
        assert retried['status'] == 'running'
        assert len(calls) == 2
        assert retried['transcripts'][0]['messages'] == [
            {'role': 'user', 'content': 'Why does detail 2 matter?'}]
        assert Decimal(retried['session_usage']['cost_usd']) == cost + Decimal(".001")


def test_batch_keeps_saved_workflow_sections(classroom, db_session):
    client, study_id, _ = classroom
    study = db_session.scalar(select(Study).where(Study.public_id == study_id))
    before = [(s.section_key, s.value_json, s.status) for s in db_session.scalars(select(StudySectionState).where(StudySectionState.study_id == study.id))]
    finish(client, study_id, start(client, study_id).json()['data']['batch'])
    db_session.expire_all()
    after = [(s.section_key, s.value_json, s.status) for s in db_session.scalars(select(StudySectionState).where(StudySectionState.study_id == study.id))]
    assert before == after


def chat(client, study_id, **extra):
    return client.post(f'/api/v1/studies/{study_id}/interview/chat', json={
        'persona_id': load_persona_seed_rows()[0]['persona_id'], 'prompt': 'What matters?',
        'standalone': True, 'model': MODEL, **extra})


def regen(client, study_id, answer_id, version=0, **extra):
    return client.post(f'/api/v1/studies/{study_id}/interview/answers/{answer_id}/regenerate', json={'version': version, **extra})


def test_regenerate_cached_chat_exact_context_updates_cache_and_one_persisted_answer(classroom, db_session):
    client, study_id, calls = classroom
    initial = chat(client, study_id).json()['data']['interview_chat']
    cached = chat(client, study_id).json()['data']['interview_chat']
    assert cached['cache_hit']
    assert len(calls) == 1
    fresh = regen(client, study_id, cached['answer_id']).json()['data']['answer']
    assert len(calls) == 2
    assert calls[0]['messages'] == calls[1]['messages']
    assert calls[0]['model'] == calls[1]['model']
    assert fresh['reply'] != initial['reply']
    assert client.app.state.settings.cache_mode == 'cache_first'
    replay = chat(client, study_id).json()['data']['interview_chat']
    assert replay['reply'] == fresh['reply']
    assert replay['cache_hit']
    assert Decimal(replay['session_usage']['cost_usd']) == 0
    assert len(calls) == 2
    turns = db_session.scalars(select(InterviewTurn).where(InterviewTurn.session_id == cached['session_id'])).all()
    assert len(turns) == 2
    assert next(t for t in turns if t.role == 'assistant').text == fresh['reply']
    with ThreadPoolExecutor(max_workers=2) as pool:
        duplicates = list(pool.map(lambda _: regen(client, study_id, cached['answer_id']), range(2)))
    assert all(r.json()['data']['answer'] == fresh for r in duplicates)
    assert len(calls) == 2


def test_regenerate_failure_preserves_cache_and_control_retry(classroom, monkeypatch):
    client, study_id, calls = classroom
    answer = chat(client, study_id).json()['data']['interview_chat']
    original = __import__('src.services.interview_service', fromlist=['x'])._call_openrouter_messages
    def fail(**kw):
        raise ConflictError('provider unavailable')
    # Failures preserve the answer but durably consume the attempt version.
    from src.services.exceptions import ConflictApiError as ConflictError
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', fail)
    assert regen(client, study_id, answer['answer_id']).status_code == 409
    assert chat(client, study_id).json()['data']['interview_chat']['reply'] == answer['reply']
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', original)
    assert regen(client, study_id, answer['answer_id'], version=1, retry=True).status_code == 200
    assert len(calls) == 2


def test_regenerate_budget_and_followup_guards(classroom):
    client, study_id, calls = classroom
    answer = chat(client, study_id).json()['data']['interview_chat']
    client.app.state.settings.llm_budget_usd = Decimal('.001')
    blocked = regen(client, study_id, answer['answer_id'])
    assert blocked.status_code == 429
    assert blocked.json()['error']['code'] == 'quota_exceeded'
    assert len(calls) == 1
    client.app.state.settings.llm_budget_usd = Decimal('.75')
    followup = chat(client, study_id, prompt='Why?', session_id=answer['session_id'], messages=[
        {'role': 'user', 'content': 'What matters?'}, {'role': 'assistant', 'content': answer['reply']}])
    assert followup.status_code == 200
    assert regen(client, study_id, answer['answer_id'], version=1, retry=True).status_code == 409
    assert len(calls) == 2


def test_regenerate_comparison_only_selected_model_and_score(classroom, db_session):
    client, study_id, calls = classroom
    response = client.post(f'/api/v1/studies/{study_id}/interview/compare', json={
        'persona_id': load_persona_seed_rows()[0]['persona_id'], 'question': 'What matters?',
        'model_ids': [MODEL, 'google/gemini-2.5-flash-lite']})
    assert response.status_code == 200, response.text
    comparison = response.json()['data']['interview_comparison']
    a, b = comparison['results']
    updated = regen(client, study_id, a['answer_id'])
    assert updated.status_code == 200, updated.text
    assert calls[0]['messages'] == calls[2]['messages']
    assert calls[0]['model'] == calls[2]['model']
    fresh = updated.json()['data']['answer']
    assert fresh['post_interview_score']['fit_tier']
    assert len(calls) == 3
    other = db_session.scalar(select(InterviewTurn).where(InterviewTurn.session_id == comparison['session_id'],
        InterviewTurn.role == 'assistant', InterviewTurn.model == b['model_id']))
    assert other.text == b['answer']


def test_batch_and_regenerate_ownership_and_session_isolation(classroom):
    client, study_id, calls = classroom
    other = client.post('/api/v1/studies', json={}).json()['data']['study']['study_id']
    batch = start(client, study_id).json()['data']['batch']
    assert client.get(f'/api/v1/studies/{other}/interview/batches/{batch["job_id"]}').status_code == 404
    assert step(client, other, batch).status_code == 404
    answer = chat(client, study_id).json()['data']['interview_chat']
    assert regen(client, other, answer['answer_id']).status_code == 404
    assert chat(client, other, session_id=answer['session_id']).status_code == 404
    assert chat(client, study_id, session_id=batch['job_id']).status_code == 409
    assert len(calls) == 1


def test_batch_selected_models_and_class_budget_stop(classroom, db_session):
    client, study_id, calls = classroom
    batch = start(client, study_id, interviewer_model='google/gemini-2.5-flash-lite').json()['data']['batch']
    batch = step(client, study_id, batch).json()['data']['batch']
    batch = step(client, study_id, batch).json()['data']['batch']
    assert [c['model'] for c in calls] == ['google/gemini-2.5-flash-lite', MODEL]
    # Prior measured class spend exhausts the shared cap even though this run has room.
    study = db_session.scalar(select(Study).where(Study.public_id == study_id))
    db_session.add(InterviewTurn(study_id=study.id, persona_id='neo-001', session_id='other-session',
        role='assistant', text='Earlier', model=MODEL, tokens_in=1, tokens_out=1, cost_usd=Decimal('22.499')))
    db_session.commit()
    stopped = step(client, study_id, batch)
    assert stopped.status_code == 429
    assert stopped.json()['error']['details']['scope'] == 'class'
    assert len(calls) == 2


def test_batch_zero_budget_kill_switch_before_any_provider_call(classroom):
    client, study_id, calls = classroom
    client.app.state.settings.llm_budget_usd = Decimal('0')
    batch = start(client, study_id).json()['data']['batch']
    assert step(client, study_id, batch).status_code == 429
    assert calls == []


def test_classroom_identity_owns_batch_and_regenerate_routes(classroom):
    client, _, calls = classroom
    alice = {'x-authenticated-user-id': 'classroom:alice', 'x-authenticated-auth-mode': 'classroom-no-login'}
    bob = {'x-authenticated-user-id': 'classroom:bob', 'x-authenticated-auth-mode': 'classroom-no-login'}
    study_id = client.post('/api/v1/studies', headers=alice, json={}).json()['data']['study']['study_id']
    path = f'/api/v1/studies/{study_id}/interview'
    payload = {'request_id': str(uuid4()), 'persona_count': 3, 'interviewer_model': MODEL, 'interviewee_model': MODEL}
    batch = client.post(f'{path}/batches', headers=alice, json=payload).json()['data']['batch']
    assert client.get(f'{path}/batches/{batch["job_id"]}', headers=alice).status_code == 200
    assert client.get(f'{path}/batches/{batch["job_id"]}', headers=bob).status_code == 403
    assert client.post(f'{path}/batches', headers=bob, json=payload).status_code == 403
    assert client.post(f'{path}/batches/{batch["job_id"]}/advance', headers=bob, json={'revision': 0}).status_code == 403
    answer = client.post(f'{path}/chat', headers=alice, json={'persona_id': load_persona_seed_rows()[0]['persona_id'],
        'standalone': True, 'model': MODEL, 'prompt': 'What matters?'}).json()['data']['interview_chat']
    assert client.post(f'{path}/answers/{answer["answer_id"]}/regenerate', headers=bob, json={'version': 0}).status_code == 403
    assert len(calls) == 1


@pytest.mark.parametrize("activity", ["regenerate", "chat", "comparison"])
def test_concurrent_batch_and_regenerate_share_class_budget(classroom, db_session, activity):
    client, study_id, calls = classroom
    answer = chat(client, study_id).json()['data']['interview_chat']
    batch = start(client, study_id).json()['data']['batch']
    batch = step(client, study_id, batch).json()['data']['batch']
    study = db_session.scalar(select(Study).where(Study.public_id == study_id))
    db_session.add(InterviewTurn(study_id=study.id, persona_id='neo-001', session_id='class-usage',
        role='assistant', text='Earlier', model=MODEL, tokens_in=1, tokens_out=1, cost_usd=Decimal('22.497')))
    db_session.commit()
    def other_call():
        if activity == "regenerate":
            return regen(client, study_id, answer['answer_id'])
        if activity == "chat":
            return chat(client, study_id, prompt='New question', session_id=answer['session_id'])
        return client.post(f'/api/v1/studies/{study_id}/interview/compare', json={
            'persona_id': load_persona_seed_rows()[0]['persona_id'], 'question': 'Another question',
            'model_ids': [MODEL, 'google/gemini-2.5-flash-lite']})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(step, client, study_id, batch), pool.submit(other_call)]
        responses = [f.result() for f in futures]
    assert sorted(r.status_code for r in responses) == [200, 429]
    assert len(calls) == 3


def test_batch_network_failure_is_not_automatically_retried(classroom, monkeypatch):
    client, study_id, calls = classroom
    import requests
    attempts = []
    def fail(*args, **kwargs):
        attempts.append(kwargs)
        raise requests.Timeout('Response lost')
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', real_provider)
    monkeypatch.setattr('src.services.interview_service.requests.post', fail)
    batch = start(client, study_id).json()['data']['batch']
    failed = step(client, study_id, batch).json()['data']['batch']
    assert failed['status'] == 'failed'
    assert 'retrying can incur another charge' in failed['error']['message']
    assert len(attempts) == 1


@pytest.mark.parametrize("activity", ["chat", "comparison"])
def test_duplicate_chat_and_comparison_do_not_repeat_paid_calls(classroom, activity):
    client, study_id, calls = classroom
    def submit():
        if activity == "chat":
            return chat(client, study_id)
        return client.post(f'/api/v1/studies/{study_id}/interview/compare', json={
            'persona_id': load_persona_seed_rows()[0]['persona_id'], 'question': 'What matters?',
            'model_ids': [MODEL, 'google/gemini-2.5-flash-lite']})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert len(calls) == (1 if activity == 'chat' else 2)


def test_failed_advance_requires_explicit_retry(classroom, monkeypatch):
    from threading import Event
    from src.services import interview_service
    client, study_id, calls = classroom
    batch = start(client, study_id).json()['data']['batch']
    accepted, release, duplicate_submitted = Event(), Event(), Event()
    attempts = []
    original = interview_service._call_openrouter_messages
    def timeout(**kwargs):
        attempts.append(kwargs)
        accepted.set()
        assert release.wait(5)
        raise RuntimeError('Accepted by provider, response lost')
    monkeypatch.setattr(interview_service, '_call_openrouter_messages', timeout)
    def duplicate():
        duplicate_submitted.set()
        return step(client, study_id, batch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(step, client, study_id, batch)
        assert accepted.wait(5)
        second = pool.submit(duplicate)
        assert duplicate_submitted.wait(5)
        release.set()
        failed = first.result().json()['data']['batch']
        assert second.result().json()['data']['batch'] == failed
    assert len(attempts) == 1
    assert failed['revision'] == batch['revision'] + 1
    assert step(client, study_id, failed).json()['data']['batch'] == failed
    assert step(client, study_id, batch, retry=True).json()['data']['batch'] == failed
    assert len(attempts) == 1
    monkeypatch.setattr(interview_service, '_call_openrouter_messages', original)
    resumed = step(client, study_id, failed, retry=True).json()['data']['batch']
    assert resumed['status'] == 'running'
    assert len(calls) == 1


def test_batch_daily_run_limit_counts_creation_once(classroom, db_session):
    from src.persistence.models import UserUsageCounter
    from src.services.usage_limits import METRIC_INTERVIEW_RUN
    client, study_id, calls = classroom
    client.app.state.settings.daily_provider_run_limit = 1
    request_id = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(client, study_id, request_id=request_id), range(2)))
    assert all(r.status_code == 200 for r in results)
    batch = results[0].json()['data']['batch']
    assert results[1].json()['data']['batch']['job_id'] == batch['job_id']
    finish(client, study_id, batch)
    assert start(client, study_id, request_id=request_id).status_code == 200
    other_study = client.post('/api/v1/studies', json={}).json()['data']['study']['study_id']
    rejected = start(client, other_study)
    assert rejected.status_code == 429
    assert rejected.json()['error']['details']['metric_key'] == METRIC_INTERVIEW_RUN
    counter = db_session.scalar(select(UserUsageCounter).where(UserUsageCounter.metric_key == METRIC_INTERVIEW_RUN))
    assert counter.count == 1
    assert len(calls) == 48


def test_batch_history_preserves_completed_and_paused_owned_runs(classroom):
    client, study_id, _ = classroom
    completed = finish(client, study_id, start(client, study_id).json()['data']['batch'])
    paused = step(client, study_id, start(client, study_id).json()['data']['batch']).json()['data']['batch']
    history = client.get(f'/api/v1/studies/{study_id}/interview/batches').json()['data']['batches']
    assert history == [paused, completed]
    assert completed['transcripts'] and completed['session_usage']['cost_usd'] != '0'
    other = client.post('/api/v1/studies', json={}).json()['data']['study']['study_id']
    assert client.get(f'/api/v1/studies/{other}/interview/batches').json()['data']['batches'] == []
    bob = {'x-authenticated-user-id': 'classroom:bob', 'x-authenticated-auth-mode': 'classroom-no-login'}
    assert client.get(f'/api/v1/studies/{study_id}/interview/batches', headers=bob).status_code == 403


def test_concurrent_distinct_batches_share_daily_run_limit(classroom):
    client, study_id, calls = classroom
    client.app.state.settings.daily_provider_run_limit = 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(client, study_id), range(2)))
    assert sorted(r.status_code for r in results) == [200, 429]
    assert calls == []


def test_failed_regeneration_requires_explicit_retry_and_attempt_audit(classroom, monkeypatch, db_session):
    from threading import Event
    from src.services import interview_service
    client, study_id, calls = classroom
    answer = chat(client, study_id).json()['data']['interview_chat']
    accepted, release, submitted = Event(), Event(), Event()
    attempts = []
    original = interview_service._call_openrouter_messages
    def timeout(**kwargs):
        attempts.append(kwargs)
        accepted.set()
        assert release.wait(5)
        raise RuntimeError('Accepted by provider, response lost')
    monkeypatch.setattr(interview_service, '_call_openrouter_messages', timeout)
    def duplicate():
        submitted.set()
        return regen(client, study_id, answer['answer_id'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(regen, client, study_id, answer['answer_id'])
        assert accepted.wait(5)
        second = pool.submit(duplicate)
        assert submitted.wait(5)
        release.set()
        failed = first.result()
        duplicate_result = second.result()
    assert failed.status_code == duplicate_result.status_code == 503
    for key in ('code', 'message', 'details'):
        assert failed.json()['error'][key] == duplicate_result.json()['error'][key]
    assert failed.json()['error']['details']['version'] == 1
    assert regen(client, study_id, answer['answer_id'], version=1).status_code == 503
    assert regen(client, study_id, answer['answer_id'], retry=True).status_code == 503
    assert len(attempts) == 1
    assert chat(client, study_id).json()['data']['interview_chat']['reply'] == answer['reply']
    monkeypatch.setattr(interview_service, '_call_openrouter_messages', original)
    fresh = regen(client, study_id, answer['answer_id'], version=1, retry=True).json()['data']['answer']
    assert fresh['version'] == 2
    assert len(calls) == 2
    records = db_session.scalars(select(Job).where(Job.job_type == 'interview_regeneration').order_by(Job.queued_at)).all()
    assert len(records) == 2  # Rejected duplicates never create another attempt.
    study = db_session.scalar(select(Study).where(Study.public_id == study_id))
    for record in records:
        assert record.study_id == study.id
        assert record.payload_json['answer_id'] == answer['answer_id']
        assert record.payload_json['session_id'] == answer['session_id']
        assert record.payload_json['model'] == MODEL
        assert record.payload_json['owner_user_id'] == str(study.owner_user_id)
        assert record.payload_json['turn_id']
        assert record.started_at and record.completed_at
    assert records[0].status == 'failed'
    assert records[0].result_json == {'outcome': 'unknown', 'incremental_cost_usd': None}
    assert records[1].status == 'completed'
    assert Decimal(records[1].result_json['incremental_cost_usd']) == Decimal('.001')


@pytest.mark.parametrize('surface', ['chat', 'comparison'])
def test_dependent_followup_blocks_regeneration(classroom, surface):
    client, study_id, calls = classroom
    if surface == 'chat':
        answer = chat(client, study_id).json()['data']['interview_chat']
    else:
        comparison = client.post(f'/api/v1/studies/{study_id}/interview/compare', json={
            'persona_id': load_persona_seed_rows()[0]['persona_id'], 'question': 'What matters?',
            'model_ids': [MODEL, 'google/gemini-2.5-flash-lite']}).json()['data']['interview_comparison']
        answer = {**comparison['results'][0], 'session_id': comparison['session_id'],
                  'reply': comparison['results'][0]['answer']}
    assert chat(client, study_id, prompt='Why?', session_id=answer['session_id'], messages=[
        {'role': 'user', 'content': 'What matters?'},
        {'role': 'assistant', 'content': answer['reply']}]).status_code == 200
    before = len(calls)
    assert regen(client, study_id, answer['answer_id']).status_code == 409
    assert len(calls) == before


def test_budget_stop_returns_committed_chat_answer(classroom, db_session, monkeypatch):
    client, study_id, calls = classroom
    first = chat(client, study_id).json()['data']['interview_chat']
    def costly(**kw):
        return InterviewAnswer(text='Committed overrun answer', model=kw['model'], tokens_in=10,
                               tokens_out=5, cost_usd=Decimal('1'))
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', costly)
    response = chat(client, study_id, prompt='Why?', session_id=first['session_id'], messages=[
        {'role': 'assistant', 'content': first['reply']}])
    assert response.status_code == 429
    committed = response.json()['error']['details']['committed_answer']
    assert committed['reply'] == 'Committed overrun answer'
    assert committed['version'] == 0
    job = db_session.scalar(select(Job).where(Job.public_id == committed['answer_id']))
    assert db_session.get(InterviewTurn, UUID(job.payload_json['turn_id'])).text == committed['reply']
    assert Decimal(committed['session_usage']['cost_usd']) == Decimal('1.001')
    assert regen(client, study_id, first['answer_id']).status_code == 409


@pytest.mark.parametrize('activity', ['regenerate', 'batch_question', 'batch_answer'])
def test_reasoning_only_response_records_measured_cost(classroom, monkeypatch, db_session, activity):
    import requests
    from src.services.llm_budget import load_interview_budget_snapshot

    client, study_id, _ = classroom
    if activity == 'regenerate':
        original = chat(client, study_id).json()['data']['interview_chat']
        session_id = original['session_id']
    else:
        original = start(client, study_id).json()['data']['batch']
        # Preserve an existing displayed answer, exercising both batch roles.
        for _ in range(2 if activity == 'batch_question' else 3):
            original = step(client, study_id, original).json()['data']['batch']
        session_id = original['job_id']
    before = load_interview_budget_snapshot(db_session, session_id=session_id,
                                           run_budget_usd=client.app.state.settings.llm_budget_usd)
    attempts = []
    def reasoning_only(*args, **kwargs):
        attempts.append(kwargs)
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"model":"qwen/qwen3.7-plus","choices":[{"message":{"content":"<think>Private reasoning only</think>"}}],"usage":{"prompt_tokens":123,"completion_tokens":456,"cost":0.012345}}'
        return response
    from src.services import interview_service
    successful_provider = interview_service._call_openrouter_messages
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', real_provider)
    monkeypatch.setattr('src.services.interview_service.requests.post', reasoning_only)

    if activity == 'regenerate':
        failed = regen(client, study_id, original['answer_id'])
        assert failed.status_code == 503
        saved = db_session.scalar(select(Job).where(Job.public_id == original['answer_id']))
        db_session.refresh(saved)
        assert saved.result_json['reply'] == original['reply']
        turn = db_session.get(InterviewTurn, UUID(saved.payload_json['turn_id']))
        db_session.refresh(turn)
        assert turn.text == original['reply']
        assert turn.cost_usd == before.run_spent_usd
        assert chat(client, study_id).json()['data']['interview_chat']['reply'] == original['reply']
    else:
        failed = step(client, study_id, original).json()['data']['batch']
        assert failed['status'] == 'failed'
        retrieved = client.get(f'/api/v1/studies/{study_id}/interview/batches/{session_id}').json()['data']['batch']
        assert retrieved['transcripts'] == original['transcripts']

    after = load_interview_budget_snapshot(db_session, session_id=session_id,
                                          run_budget_usd=client.app.state.settings.llm_budget_usd)
    assert after.run_spent_usd == before.run_spent_usd + Decimal('0.012345')
    assert after.class_spent_usd == before.class_spent_usd + Decimal('0.012345')
    charged = db_session.scalar(select(InterviewTurn).where(
        InterviewTurn.session_id == session_id, InterviewTurn.cost_usd == Decimal('0.012345')))
    assert charged.text == ''
    assert (charged.tokens_in, charged.tokens_out, charged.model) == (123, 456, 'qwen/qwen3.7-plus')
    assert len(attempts) == 1

    if activity == 'regenerate':
        monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', successful_provider)
        assert regen(client, study_id, original['answer_id'], version=1, retry=True).status_code == 200
