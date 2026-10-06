"""Pre-recorded classroom playback. No provider or quota work belongs here."""
from copy import deepcopy
import hashlib
import json
import logging
from pathlib import Path
from sqlalchemy import select
from src.persistence.models import Job
from src.services.exceptions import ConflictApiError
from src.services.standalone_interview import serialized_local

LABEL = "Demo session - pre-recorded, no AI"
READ_ONLY = "Demo (no AI): read-only"
FIXTURES = Path(__file__).resolve().parents[2] / "seed_data" / "demo"
KINDS = {"focus-group": "focus_group_room", "batch": "standalone_batch", "you": "interview_session"}
ZERO_USAGE = {"cost_usd": "0", "tokens_in": 0, "tokens_out": 0, "provider_call_count": 0}


def refuse_demo(job):
    if job and (job.payload_json or {}).get("demo"):
        raise ConflictApiError(READ_ONLY)


def refuse_demo_session(session, session_id):
    if session_id:
        refuse_demo(session.scalar(select(Job).where(Job.public_id == session_id)))


def load_fixture(kind):
    try:
        data = json.loads((FIXTURES / f"{kind}.json").read_text())
        def require(condition):
            if not condition:
                raise ValueError("Invalid demo fixture")

        require(data["kind"] == kind and isinstance(data["config"], dict))
        require(type(data["provisional"]) is bool)
        config, state = data["config"], data["state"]
        if kind == "focus-group":
            from src.services.focus_group import STAGES
            ids = config["persona_ids"]
            require(6 <= len(ids) <= 8 and len(set(ids)) == len(ids))
            require(all(config["demo_cards"][pid] for pid in ids))
            require(type(config["max_rounds"]) is int and config["max_rounds"] >= 5)
            require(state["stage_index"] == 4 and type(state["revision"]) is int)
            rounds = state["rounds"]
            require({r["stage"] for r in rounds} == set(STAGES))
            for index, round_ in enumerate(rounds):
                require(round_["index"] == index and bool(round_["question"]))
                require(round_["kind"] in {"core", "probe"})
                require({a["persona_id"] for a in round_["answers"]} == set(ids))
                require(all(a["status"] in {"answered", "silent"} for a in round_["answers"]))
                require(all(isinstance(a["text"], str) and a["text"] for a in round_["answers"] if a["status"] == "answered"))
            concept = next(i for i, r in enumerate(rounds) if r.get("stimulus", {}).get("kind") == "concept")
            price = next(i for i, r in enumerate(rounds) if r.get("stimulus", {}).get("kind") == "price")
            require(concept < price and any(r["stage"] == "price_reactions" for r in rounds[:price]))
            require(any(r.get("recipients") and r["kind"] == "probe" for r in rounds))
        else:
            transcripts = state["transcripts"] if kind == "batch" else [{"messages": state["messages"]}]
            if kind == "batch":
                require(len(transcripts) >= 6 and config["persona_count"] == len(transcripts))
                require(state["completed_personas"] == len(transcripts) and config["turn_limit"] == 8)
                require(type(state["revision"]) is int)
            for transcript in transcripts:
                messages = transcript["messages"]
                require(len(messages) == 16)
                require(all(m["role"] == ("user" if i % 2 == 0 else "assistant") and
                            isinstance(m["content"], str) and m["content"].strip() for i, m in enumerate(messages)))
            if kind == "batch" and state.get("insights"):
                from types import SimpleNamespace
                from src.services.standalone_themes import corpus, validate
                _, pairs = corpus(SimpleNamespace(result_json=state))
                require(validate(state["insights"], pairs) is None)
        return data
    except (OSError, ValueError, KeyError, TypeError, AssertionError, StopIteration, AttributeError) as exc:
        logging.getLogger(__name__).error("Invalid demo fixture: %s.json; run scripts/make_demo_fixtures.py", kind)
        raise ConflictApiError(f"Demo {kind} unavailable: operator must run apps/api/scripts/make_demo_fixtures.py and deploy seed_data/demo/{kind}.json. No live run was started.") from exc


@serialized_local
def open_demo(session, settings, study, kind):
    from src.services.interview_cache import _lock_cache_key_for_transaction
    from src.services.ids import make_public_id
    from src.services.focus_group import room_status
    from src.services.standalone_interview import batch_status
    if kind not in KINDS:
        raise ConflictApiError("Unknown demo example.")
    _lock_cache_key_for_transaction(session, hashlib.sha256(f"demo:{study.id}:{kind}".encode()).hexdigest())
    jobs = session.scalars(select(Job).where(Job.study_id == study.id, Job.job_type == KINDS[kind], Job.status != "deleted"))
    job = next((j for j in jobs if (j.payload_json or {}).get("demo_kind") == kind), None)
    if not job:
        fixture = load_fixture(kind)  # Validate before inserting anything.
        job = Job(public_id=make_public_id("you" if kind == "you" else "demo"), study_id=study.id,
                  job_type=KINDS[kind], status="completed",
                  payload_json={**deepcopy(fixture["config"]), "demo": True, "demo_kind": kind,
                                "demo_label": LABEL, "provisional": fixture.get("provisional", False),
                                "estimated_cost_usd": "0"}, result_json=deepcopy(fixture["state"]))
        session.add(job)
        session.commit()
    if kind == "focus-group":
        return {"room": room_status(session, settings, study, job.public_id)}
    if kind == "batch":
        return {"batch": batch_status(session, settings, study, job.public_id)}
    return {"interview": {**job.result_json, "demo": True, "provisional": job.payload_json.get("provisional"),
                          "demo_label": LABEL, "rehearsal_label": "Synthetic rehearsal - not PA3.5 live fieldwork",
                          "sessionId": job.public_id, "ended": True, "costUsd": "0", "turnLimit": 8}}
