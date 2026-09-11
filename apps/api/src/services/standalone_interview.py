"""Durable classroom batches and single-answer replacement, independent of workflow state."""
from __future__ import annotations

from copy import deepcopy
from functools import wraps
from threading import RLock
from uuid import UUID

from sqlalchemy import select

from src.persistence.models import InterviewTurn, Job, Persona
from src.services.exceptions import ApiError, ConflictApiError, NotFoundApiError, QuotaExceededApiError, ValidationApiError
from src.services.ids import make_public_id
from src.services.interview_cache import resolve_interview_answer
from src.services.interviewer_agent import build_interviewer_messages, derive_interviewer_turn_plan
from src.services.llm_budget import enforce_budget_open, enforce_measured_cost, enforce_run_preflight, load_interview_budget_snapshot, lock_class_budget_for_transaction
from src.services.model_catalog import list_interview_model_catalog

RESEARCH_BRIEF = {
    "primary_question": "How would homeowners decide whether to buy a Tahoe Mini backyard studio?",
    "known_context": "Tahoe Mini is a compact modular backyard studio for flexible household use.",
    "decisions_to_inform": ["Understand uses, purchase barriers, and household decision making."],
}
_local_lock = RLock()


def serialized_local(fn):
    """SQLite development server equivalent of production transaction locks."""
    @wraps(fn)
    def wrapped(session, *args, **kwargs):
        if session.get_bind().dialect.name == "sqlite":
            with _local_lock:
                return fn(session, *args, **kwargs)
        return fn(session, *args, **kwargs)
    return wrapped


def validate_session(session, study, session_id):
    import hashlib
    from src.services.interview_cache import _lock_cache_key_for_transaction
    _lock_cache_key_for_transaction(session, hashlib.sha256(f"session:{session_id}".encode()).hexdigest())
    foreign = session.scalar(select(InterviewTurn.id).where(
        InterviewTurn.session_id == session_id, InterviewTurn.study_id != study.id).limit(1))
    batch = session.scalar(select(Job).where(Job.public_id == session_id))
    if foreign or (batch and batch.study_id != study.id):
        raise NotFoundApiError("Interview session not found.")
    if batch is None:
        session.add(Job(public_id=session_id, study_id=study.id, job_type="interview_session",
                        status="active", payload_json={}))
        session.flush()
    if batch and batch.job_type == "standalone_batch":
        raise ConflictApiError("Batch sessions can only be advanced through the batch endpoint.")


def validate_models(model_ids, allow_expensive):
    catalog = {m["id"]: m for m in list_interview_model_catalog()["models"]}
    if any(not isinstance(m, str) or m not in catalog for m in model_ids):
        raise ValidationApiError("Select models from the curated interview catalog.")
    if allow_expensive is not True and any(catalog[m]["tier"] == "expensive" for m in model_ids):
        raise ValidationApiError("Expensive interview models require explicit opt-in.")


def remember_answer(session, study, *, persona_id, model, question, prior_turns, turn, comparison=False):
    """Save original request inputs, including the requested (not provider-alias) model."""
    from src.services.interview_service import utcnow
    session.flush()
    job = Job(public_id=make_public_id("ans"), study_id=study.id, job_type="interview_answer", status="completed",
              payload_json={"persona_id": persona_id, "model": model, "question": question,
                            "prior_turns": prior_turns, "turn_id": str(turn.id), "comparison": comparison},
              result_json={"version": 0, "reply": turn.text}, queued_at=utcnow())
    session.add(job)
    session.flush()
    return job.public_id


def owned_job(session, study, public_id, kind, *, lock=False):
    query = select(Job).where(Job.public_id == public_id, Job.study_id == study.id, Job.job_type == kind)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    job = session.scalar(query)
    if not job:
        raise NotFoundApiError("Interview operation not found.")
    return job


def usage(session, settings, session_id):
    from src.services.interview_service import _serialize_session_usage
    return _serialize_session_usage(load_interview_budget_snapshot(session, session_id=session_id, run_budget_usd=settings.llm_budget_usd))


@serialized_local
def regenerate_answer(session, settings, study, answer_id, payload):
    from src.services import interview_service as service
    from src.services.interview_scoring import score_persisted_interview_transcript
    job = owned_job(session, study, answer_id, "interview_answer")
    original_turn = session.get(InterviewTurn, UUID(job.payload_json["turn_id"]))
    if not original_turn or original_turn.study_id != study.id:
        raise NotFoundApiError()
    validate_session(session, study, original_turn.session_id)
    session.refresh(original_turn)
    job = owned_job(session, study, answer_id, "interview_answer", lock=True)
    context = job.payload_json
    validate_models([context["model"]], payload.get("allow_expensive_models"))
    expected = payload.get("version")
    if type(expected) is not int or expected < 0:
        raise ValidationApiError("A non-negative answer version is required.")
    if job.status == "failed" and (expected < job.result_json["version"] or
                                   (expected == job.result_json["version"] and payload.get("retry") is not True)):
        error = job.error_json
        raise ApiError(error["status_code"], error["code"], error["message"], error["details"])
    if expected < job.result_json["version"]:
        return job.result_json  # Retried/double-clicked replacement already completed.
    if expected != job.result_json["version"]:
        raise ConflictApiError("Answer version is out of date.")
    turn = session.get(InterviewTurn, UUID(context["turn_id"]))
    if not turn or turn.study_id != study.id:
        raise NotFoundApiError()
    # Comparison siblings are independent; later chat answers depend on this context.
    independent_ids = [UUID(answer.payload_json["turn_id"]) for answer in session.scalars(
        select(Job).where(Job.study_id == study.id, Job.job_type == "interview_answer"))
        if answer.payload_json.get("comparison")]
    if session.scalar(select(InterviewTurn.id).where(
        InterviewTurn.role == "assistant", InterviewTurn.id.not_in(independent_ids),
        InterviewTurn.session_id == turn.session_id, InterviewTurn.study_id == study.id,
        InterviewTurn.created_at > turn.created_at).limit(1)):
        raise ConflictApiError("Only the latest answer can be regenerated once follow-ups exist.")
    budget_error = None
    provider_started = False
    attempt = Job(public_id=make_public_id("regen"), study_id=study.id,
        job_type="interview_regeneration", status="running", queued_at=service.utcnow(),
        started_at=service.utcnow(), payload_json={"answer_id": answer_id, "version": expected,
            "turn_id": str(turn.id), "session_id": turn.session_id, "model": context["model"],
            "persona_id": context["persona_id"], "owner_user_id": str(study.owner_user_id)})
    session.add(attempt)

    def provider():
        nonlocal budget_error, provider_started
        lock_class_budget_for_transaction(session)
        snapshot = load_interview_budget_snapshot(session, session_id=turn.session_id, run_budget_usd=settings.llm_budget_usd)
        enforce_budget_open(snapshot)
        if snapshot.run_provider_call_count == 0:
            model = next(m for m in list_interview_model_catalog()["models"] if m["id"] == context["model"])
            enforce_run_preflight(estimated_cost_usd=model["estimated_cost_per_persona_usd"],
                class_spent_usd=snapshot.class_spent_usd, run_budget_usd=snapshot.run_budget_usd)
        if not settings.openrouter_api_key:
            raise ConflictApiError("OPENROUTER_API_KEY is not configured.")
        provider_started = True
        # ponytail: process death after provider acceptance can lose this attempt before
        # commit; explicit recovery may pay twice. Classroom scope accepts this window
        # under the existing budget caps (not a strict ceiling on unreported charges).
        # Add a durable two-phase pending-attempt ledger before unattended/volume use
        # or materially higher per-call spend. See the plan's accepted durability risk.
        result = service._call_openrouter_messages(api_key=settings.openrouter_api_key or "", model=context["model"],
            messages=[*context["prior_turns"], {"role": "user", "content": context["question"]}], timeout=90, max_attempts=1)
        try:
            enforce_measured_cost(snapshot, cost_usd=result.cost_usd)
        except QuotaExceededApiError as exc:
            budget_error = exc
        return result

    try:
        answer = resolve_interview_answer(session, cache_mode=settings.cache_mode, regenerate=True,
            persona_id=context["persona_id"], model=context["model"], question=context["question"],
            prior_turns=context["prior_turns"], call_provider=provider)
    except Exception as exc:
        from src.services.exceptions import ProviderUnavailableApiError
        error = exc if isinstance(exc, ApiError) else ProviderUnavailableApiError(str(exc))
        message = error.message
        if provider_started:
            message += " The provider outcome may be unknown; retrying can incur another charge."
        message += " Your previous answer is preserved."
        details = {**error.details, "answer_id": answer_id, "version": expected + 1, "retry_required": True}
        job.status = "failed"
        job.result_json = {**job.result_json, "version": expected + 1}
        job.error_json = {"status_code": error.status_code, "code": error.code, "message": message, "details": details}
        attempt.status = "failed"
        attempt.completed_at = service.utcnow()
        attempt.error_json = job.error_json
        attempt.result_json = {"outcome": "unknown" if provider_started else "rejected",
                               "incremental_cost_usd": None if provider_started else "0"}
        session.commit()
        raise ApiError(error.status_code, error.code, message, details) from exc
    # Keep all incurred spend while replacing only the selected transcript text.
    turn.text = answer.text
    turn.cost_usd += answer.cost_usd
    turn.tokens_in += answer.tokens_in
    turn.tokens_out += answer.tokens_out
    session.flush()
    score = score_persisted_interview_transcript(session, study_id=study.id, persona_id=turn.persona_id,
                                              session_id=turn.session_id, model=turn.model)
    result = {"answer_id": answer_id, "version": expected + 1, "reply": answer.text,
              "post_interview_score": score, "session_usage": usage(session, settings, turn.session_id),
              "budget_stop": {"code": budget_error.code, "message": budget_error.message, "details": budget_error.details} if budget_error else None}
    job.result_json = result
    job.status = "completed"
    job.error_json = None
    attempt.status = "completed"
    attempt.completed_at = service.utcnow()
    attempt.result_json = {"outcome": "completed", "incremental_cost_usd": str(answer.cost_usd),
                           "tokens_in": answer.tokens_in, "tokens_out": answer.tokens_out}
    session.commit()
    return result


def batch_status(session, settings, study, job_id):
    job = owned_job(session, study, job_id, "standalone_batch")
    return {"job_id": job.public_id, "status": job.status, **job.payload_json, **(job.result_json or {}),
            "error": job.error_json, "session_usage": usage(session, settings, job.public_id)}


def list_batches(session, settings, study):
    jobs = session.scalars(select(Job).where(
        Job.study_id == study.id, Job.job_type == "standalone_batch"
    ).order_by(Job.queued_at.desc())).all()
    return [batch_status(session, settings, study, job.public_id) for job in jobs]


@serialized_local
def start_batch(session, settings, study, payload):
    from src.services.interview_service import utcnow
    count = payload.get("persona_count")
    interviewer, interviewee = payload.get("interviewer_model"), payload.get("interviewee_model")
    validate_models([interviewer, interviewee], payload.get("allow_expensive_models"))
    try:
        plan = derive_interviewer_turn_plan(persona_count=count, interviewer_model=interviewer, interviewee_model=interviewee)
    except ValueError as exc:
        raise ValidationApiError(str(exc)) from exc
    personas = session.scalars(select(Persona).order_by(Persona.row_index).limit(count)).all()
    if len(personas) != count:
        raise ValidationApiError("The requested fixed personas are unavailable.")
    # Client supplies a stable request ID so a lost creation response is recoverable.
    try:
        request_id = str(UUID(str(payload.get("request_id"))))
    except ValueError as exc:
        raise ValidationApiError("request_id must be a UUID.") from exc
    import hashlib
    public_id = "batch_" + hashlib.sha256(f"{study.id}:{request_id}".encode()).hexdigest()[:40]
    # Serialize creation, including the absent-row case, before checking idempotency.
    from src.services.interview_cache import _lock_cache_key_for_transaction
    _lock_cache_key_for_transaction(session, hashlib.sha256(public_id.encode()).hexdigest())
    existing = session.scalar(select(Job).where(Job.public_id == public_id))
    config = {"persona_count": count, "persona_ids": [p.persona_id for p in personas],
              "interviewer_model": interviewer, "interviewee_model": interviewee,
              "estimated_cost_usd": str(plan.estimated_run_cost_usd), "turn_limit": plan.turn_limit}
    if existing:
        if existing.payload_json != config:
            raise ConflictApiError("This batch request ID was already used with different settings.")
        return batch_status(session, settings, study, public_id)
    if study.owner_user_id:
        from src.services.usage_limits import consume_daily_quota, METRIC_INTERVIEW_RUN
        consume_daily_quota(session, settings, owner_user_id=study.owner_user_id,
                            metric_key=METRIC_INTERVIEW_RUN)
    job = Job(public_id=public_id, study_id=study.id, job_type="standalone_batch", status="running",
              payload_json=config, result_json={"revision": 0, "transcripts": [], "completed_personas": 0},
              queued_at=utcnow(), started_at=utcnow())
    session.add(job)
    session.commit()
    return batch_status(session, settings, study, public_id)


@serialized_local
def advance_batch(session, settings, study, job_id, payload):
    """Exactly one provider/cache call per revision; progress and usage commit together."""
    from src.services import interview_service as service
    job = owned_job(session, study, job_id, "standalone_batch", lock=True)
    state = deepcopy(job.result_json)
    if type(payload.get("revision")) is not int:
        raise ValidationApiError("An integer batch revision is required.")
    if payload["revision"] != state["revision"] or job.status in {"completed", "budget_stopped"}:
        return batch_status(session, settings, study, job_id)
    if job.status == "failed" and payload.get("retry") is not True:
        return batch_status(session, settings, study, job_id)
    config = job.payload_json
    index = state["completed_personas"]
    persona_id = config["persona_ids"][index]
    if len(state["transcripts"]) == index:
        state["transcripts"].append({"persona_id": persona_id, "messages": []})
    transcript = state["transcripts"][index]["messages"]
    asking = len(transcript) % 2 == 0
    model = config["interviewer_model" if asking else "interviewee_model"]
    if asking:
        prior = build_interviewer_messages(research_brief=RESEARCH_BRIEF, transcript=transcript,
            turn_number=len(transcript)//2 + 1, turn_limit=config["turn_limit"])
        question = "AI interviewer: derive the next question"
        messages = prior
    else:
        persona = session.get(Persona, persona_id)
        prior = [{"role": "system", "content": service._build_fixed_persona_system_prompt(persona.profile_json)}, *transcript[:-1]]
        question = transcript[-1]["content"]
        messages = [*prior, {"role": "user", "content": question}]
    budget_error = None

    def provider():
        nonlocal budget_error
        lock_class_budget_for_transaction(session)
        snapshot = load_interview_budget_snapshot(session, session_id=job_id, run_budget_usd=settings.llm_budget_usd)
        enforce_budget_open(snapshot)
        if snapshot.run_provider_call_count == 0:
            enforce_run_preflight(estimated_cost_usd=config["estimated_cost_usd"], class_spent_usd=snapshot.class_spent_usd,
                                  run_budget_usd=snapshot.run_budget_usd)
        if not settings.openrouter_api_key:
            raise ConflictApiError("OPENROUTER_API_KEY is not configured.")
        # ponytail: a process crash after acceptance but before commit can replay a paid
        # step. The accepted classroom estimate is ~$0.003/step, not a hard ceiling;
        # budget caps cannot account for usage never received. Upgrade to a durable
        # two-phase pending-attempt ledger for volume or order-of-magnitude cost growth.
        answer = service._call_openrouter_messages(api_key=settings.openrouter_api_key or "", model=model, messages=messages, timeout=90, max_attempts=1)
        try:
            enforce_measured_cost(snapshot, cost_usd=answer.cost_usd)
        except QuotaExceededApiError as exc:
            budget_error = exc
        return answer

    try:
        answer = resolve_interview_answer(session, cache_mode=settings.cache_mode, persona_id=persona_id,
            model=model, question=question, prior_turns=prior, call_provider=provider)
        content = service.normalize_interviewer_question(answer.text) if asking else answer.text
        transcript.append({"role": "user" if asking else "assistant", "content": content})
        session.add(InterviewTurn(study_id=study.id, persona_id=persona_id, session_id=job_id,
            role="user" if asking else "assistant", text=content, model=answer.model, tokens_in=answer.tokens_in,
            tokens_out=answer.tokens_out, cost_usd=answer.cost_usd, created_at=service.utcnow()))
        if len(transcript) == config["turn_limit"] * 2:
            state["completed_personas"] += 1
        state["revision"] += 1
        job.result_json = state
        job.status = "completed" if state["completed_personas"] == config["persona_count"] else "running"
        job.error_json = None
        if budget_error:
            raise budget_error
    except Exception as exc:
        # Consume even a failed attempt: already queued requests cannot authorize a retry.
        state["revision"] = payload["revision"] + 1
        job.status = "budget_stopped" if isinstance(exc, QuotaExceededApiError) else "failed"
        job.error_json = {"code": exc.code if isinstance(exc, ApiError) else "provider_unavailable",
                          "message": str(exc) + (" The provider outcome may be unknown; retrying can incur another charge." if not isinstance(exc, ApiError) else ""), "details": exc.details if isinstance(exc, ApiError) else {},
                          "persona_id": persona_id, "model": model, "revision": state["revision"]}
        job.result_json = state
        session.commit()
        if isinstance(exc, QuotaExceededApiError):
            exc.details["batch"] = batch_status(session, settings, study, job_id)
            raise
        return batch_status(session, settings, study, job_id)
    job.heartbeat_at = service.utcnow()
    if job.status == "completed":
        job.completed_at = service.utcnow()
    session.commit()
    return batch_status(session, settings, study, job_id)
