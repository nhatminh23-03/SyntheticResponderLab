import json
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from test_standalone_batch import classroom, start, finish
from src.persistence.models import Job
from src.services.interview_cache import InterviewAnswer
# Bound at import, before any fixture replaces the module attribute, so a test can
# put the real helper back and exercise the parser at the HTTP boundary.
from src.services.interview_service import _call_openrouter_messages as _real_openrouter_call


@pytest.fixture
def completed(classroom, monkeypatch):
    client, study, calls = classroom
    batch = finish(client, study, start(client, study).json()['data']['batch'])
    url = f'/api/v1/studies/{study}/interview/batches/{batch["job_id"]}/themes'
    extra = []
    themes = [{'label': f'Theme {i}', 'count': 1, 'synthesis': 'An interest in the option.',
        'representative_quote': batch['transcripts'][0]['messages'][1]['content'],
        'quote_persona_id': batch['transcripts'][0]['persona_id'], 'sentiment': 'positive'} for i in range(3)]
    def provider(**kw):
        extra.append(kw)
        return InterviewAnswer(text=json.dumps({'themes': themes}), model=kw['model'],
            tokens_in=10, tokens_out=10, cost_usd=Decimal('.002'))
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', provider)
    revision = client.get(url).json()['data']['insights']['revision']
    return client, url, batch, extra, themes, {'revision': revision, 'authorize_charge': True}


def test_standalone_themes_scoped_cached(completed):
    client, url, batch, calls, themes, payload = completed
    assert not client.get(url).json()['data']['insights']['available']
    assert calls == []
    result = client.post(url, json=payload).json()['data']['insights']
    assert result['saved']['themes'] == themes
    assert result['session_usage']['cost_usd'] == '0.050'
    assert len(calls) == 1 and calls[0]['max_attempts'] == 1
    assert client.post(url, json=payload).json()['data']['insights']['available']
    assert client.get(url).json()['data']['insights']['available']
    assert len(calls) == 1
    other = client.post('/api/v1/studies', json={}).json()['data']['study']['study_id']
    assert client.get(url.replace(url.split('/')[4], other)).status_code == 404


def test_standalone_themes_explicit_authorization(completed):
    client, url, _, calls, _, payload = completed
    assert client.post(url, json={'revision': payload['revision']}).status_code == 400
    assert client.post(url, json={**payload, 'revision': 'old'}).status_code == 409
    assert calls == []


@pytest.mark.parametrize('mode', ['replay_only', 'zero', 'run', 'class'])
def test_standalone_themes_budgets(completed, mode, db_session):
    client, url, _, calls, _, payload = completed
    if mode == 'replay_only':
        client.app.state.settings.cache_mode = mode
    else:
        client.app.state.settings.llm_budget_usd = Decimal('0' if mode == 'zero' else '.048' if mode == 'run' else '.75')
        if mode == 'class':
            from src.persistence.models import InterviewTurn
            turn = db_session.scalar(select(InterviewTurn))
            turn.cost_usd = Decimal('23')
            db_session.commit()
    assert client.post(url, json=payload).status_code in (409, 429)
    assert not calls


def test_standalone_themes_concurrent(completed):
    client, url, _, calls, _, payload = completed
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: client.post(url, json=payload), range(3)))
    assert all(r.status_code == 200 for r in responses)
    assert len(calls) == 1


def test_standalone_themes_timeout_retry_and_safe_diagnostics(completed, monkeypatch, caplog):
    client, url, batch, calls, _, payload = completed
    def fail(**kw):
        calls.append(kw)
        raise RuntimeError('secret transcript credential')
    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', fail)
    with caplog.at_level('INFO'):
        response = client.post(url, json=payload).json()['data']['insights']
    assert response['saved']['outcome'] == 'unknown'
    assert 'unknown' in response['saved']['message']
    assert batch['job_id'] in caplog.text and payload['revision'] in caplog.text
    assert 'secret transcript credential' not in caplog.text
    client.post(url, json=payload)
    assert len(calls) == 1
    retry = {**payload, 'retry_attempt': response['saved']['attempt']}
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: client.post(url, json=retry), range(2)))
    assert len(calls) == 2
    assert client.get(url.removesuffix('/themes')).json()['data']['batch']['transcripts'] == batch['transcripts']


@pytest.mark.parametrize('invalid', ['quote', 'empty', 'json'])
def test_standalone_themes_malformed_preserves_cost(completed, invalid, monkeypatch):
    client, url, batch, calls, themes, payload = completed
    if invalid == 'quote': themes[0]['representative_quote'] = 'fabricated quote'
    if invalid == 'empty': themes.clear()
    if invalid == 'json':
        monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', lambda **kw:
            InterviewAnswer(text='broken json', model=kw['model'], tokens_in=10, tokens_out=1, cost_usd=Decimal('.002')))
    result = client.post(url, json=payload).json()['data']['insights']
    assert not result['available'] and result['saved']['outcome'] == 'charged'
    assert Decimal(result['session_usage']['cost_usd']) == Decimal('.050')
    assert client.get(url.removesuffix('/themes')).json()['data']['batch']['transcripts'] == batch['transcripts']


@pytest.mark.parametrize('state', ['running', 'failed', 'budget_stopped', 'empty', 'partial'])
def test_standalone_themes_availability(completed, db_session, state):
    client, url, batch, calls, _, payload = completed
    job = db_session.scalar(select(Job).where(Job.public_id == batch['job_id']))
    if state == 'empty': job.result_json = {**job.result_json, 'transcripts': []}
    elif state == 'partial': job.result_json = {**job.result_json, 'transcripts': job.result_json['transcripts'][:1]}
    else: job.status = state
    db_session.commit()
    response = client.post(url, json=payload).json()['data']['insights']
    assert not response['eligible'] and not calls


def test_standalone_themes_revision(completed, db_session):
    client, url, batch, calls, _, payload = completed
    client.post(url, json=payload)
    job = db_session.scalar(select(Job).where(Job.public_id == batch['job_id']))
    transcripts = json.loads(json.dumps(job.result_json['transcripts']))
    transcripts[0]['messages'].append({'role': 'assistant', 'content': 'A new answer'})
    job.result_json = {**job.result_json, 'transcripts': transcripts}
    db_session.commit()
    result = client.get(url).json()['data']['insights']
    assert result['stale'] and result['saved']['revision'] == payload['revision']
    assert client.post(url, json=payload).status_code == 409
    assert len(calls) == 1


@pytest.mark.parametrize('content', ['', '<think>only reasoning</think>', None])
def test_standalone_themes_unusable_content_records_measured_cost(completed, monkeypatch, content):
    """A charged call whose content cannot be used must still move the ledger.

    Refuter round 1 blocker B1. Mock at the HTTP boundary, not at
    `_call_openrouter_messages`, so the real parser runs and really raises —
    mocking the helper would skip the exact code path under test.
    """
    client, url, batch, calls, _, payload = completed
    message = {} if content is None else {'content': content}

    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self, **kw):
            return {'model': 'openai/gpt-4o-mini',
                    'choices': [{'message': message}],
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 4, 'cost': Decimal('.002')}}

    monkeypatch.setattr('src.services.interview_service._call_openrouter_messages', _real_openrouter_call)
    monkeypatch.setattr('src.services.interview_service.requests.post', lambda *a, **kw: Response())
    result = client.post(url, json=payload).json()['data']['insights']

    assert not result['available'], 'unusable content must not present themes'
    assert result['saved']['outcome'] == 'charged', 'the provider billed for this call'
    # The batch itself already spent .048; the discarded call adds its own .002.
    assert Decimal(result['session_usage']['cost_usd']) == Decimal('.050'), \
        'the measured charge must reach the ledger or the next budget check undercounts'
    assert 'billing outcome is unknown' not in result['saved']['message'], \
        'the charge is known and recorded — do not tell the student otherwise'
    assert client.get(url.removesuffix('/themes')).json()['data']['batch']['transcripts'] == batch['transcripts']
