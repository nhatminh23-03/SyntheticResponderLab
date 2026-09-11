from decimal import Decimal
from uuid import uuid4
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


def step(client, study_id, batch):
    return client.post(f'/api/v1/studies/{study_id}/interview/batches/{batch["job_id"]}/advance',
                       json={'revision': batch['revision']})


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
    assert failed['error']['revision'] == 1
    assert Decimal(failed['session_usage']['cost_usd']) == Decimal('.001')
    retrieved = client.get(f'/api/v1/studies/{study_id}/interview/batches/{batch["job_id"]}').json()['data']['batch']
    assert retrieved == failed
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', original)
    resumed = finish(client, study_id, step(client, study_id, failed).json()['data']['batch'])
    assert resumed['status'] == 'completed'
    assert len(calls) == 48


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


def regen(client, study_id, answer_id, version=0):
    return client.post(f'/api/v1/studies/{study_id}/interview/answers/{answer_id}/regenerate', json={'version': version})


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
    # ApiError renders as an HTTP failure and rolls back the replacement transaction.
    from src.services.exceptions import ConflictApiError as ConflictError
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', fail)
    assert regen(client, study_id, answer['answer_id']).status_code == 409
    assert chat(client, study_id).json()['data']['interview_chat']['reply'] == answer['reply']
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', original)
    assert regen(client, study_id, answer['answer_id']).status_code == 200
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
    assert regen(client, study_id, answer['answer_id']).status_code == 409
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
