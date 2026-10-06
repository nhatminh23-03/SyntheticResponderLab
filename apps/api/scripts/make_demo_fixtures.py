#!/usr/bin/env python3
"""Run from apps/api: python scripts/make_demo_fixtures.py [--provisional].

Uses an isolated temporary database and real classroom services, never student data.
The provider wrapper reserves a conservative token ceiling BEFORE every call, keeps
that reservation even on failure, disables retries, and stops at $2 across all demos.
Use an OpenRouter key with a $2 credit limit as the external billing ceiling too.
"""
import argparse
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from src.config.settings import AppSettings
from src.persistence.base import Base
from src.persistence.models import Job, Persona, Study
from src.persistence.persona_seed import load_persona_seed_rows, persona_cards
from src.services import focus_group as fg, standalone_interview as si, interview_service as service
from src.services.interview_cache import InterviewAnswer
from src.services.model_catalog import list_interview_model_catalog

MODEL = "openai/gpt-4o-mini"
LIMIT = Decimal("2")
OUTPUT = Path(__file__).resolve().parents[1] / "seed_data/demo"
QUESTIONS = [
    "Who lives with you, and where do you spend time at home?",
    "You mentioned sharing space. When is that most difficult?",
    "How do you handle those interruptions today?",
    "What would a separate backyard studio change for you?",
    "What would you need to learn before considering Tahoe Mini?",
    "Why does the installation uncertainty matter to you?",
    "How would you decide whether the cost is worth it?",
    "What else should we understand about your decision?",
]
ANSWERS = [
    "I am a fictional graduate student living with my parents and a younger sibling. I study at the dining table.",
    "Evenings are difficult because everyone is home and I need quiet for reading.",
    "I use headphones or go to the library, but the library closes before I finish sometimes.",
    "A separate room could help me concentrate, though it would really be my parents' purchase.",
    "I would want to know whether it fits in the yard and who handles delivery and permits.",
    "My parents had a repair project that took weeks longer than expected. They want a clear schedule.",
    "We would compare the total installed cost with improving the spare room, and how often we would use it.",
    "My sibling could use it for music too. We would need a schedule so it does not become another shared-space problem.",
]

class SpendingLimit(RuntimeError):
    pass

class CappedProvider:
    def __init__(self, provider):
        self.provider = provider
        self.reserved = Decimal("0")
        self.measured = Decimal("0")
        self.calls = 0

    def __call__(self, **kwargs):
        model = next(m for m in list_interview_model_catalog()["models"] if m["id"] == kwargs["model"])
        # One UTF-8 byte per input token, plus generous framing; output hard-capped.
        ceiling = (Decimal(len(json.dumps(kwargs["messages"], ensure_ascii=False).encode()) + 2048)
                   * Decimal(str(model["prompt_price_per_million"]))
                   + Decimal(512) * Decimal(str(model["completion_price_per_million"]))) / Decimal(1000000)
        if max(self.reserved, self.measured) + ceiling > LIMIT:
            raise SpendingLimit("$2 fixture ceiling reached; no further model calls authorized")
        self.reserved += ceiling  # Never release uncertain spend after an error.
        self.calls += 1
        result = self.provider(**{**kwargs, "max_tokens": 512, "max_attempts": 1})
        self.measured += result.cost_usd
        if self.measured > LIMIT or result.cost_usd > ceiling:
            raise SpendingLimit("Provider cost exceeded reserved ceiling; aborting fixture generation")
        return result


def provisional_provider(**kwargs):
    """Explicit handwritten placeholders. Never presented as model output."""
    prompt = kwargs["messages"]
    if "You are the interviewer conducting" in prompt[0]["content"]:
        number = int(re.search(r"TURN (\d+) OF", prompt[-1]["content"])[1])
        text = QUESTIONS[number - 1]
    else:
        text = "I would use a quiet room for work, but I need to understand the installation and total cost before deciding."
    return InterviewAnswer(text=text, model=kwargs["model"], tokens_in=0, tokens_out=0, cost_usd=Decimal("0"))


def build(provisional=False):
    with TemporaryDirectory(prefix="demo-fixtures-") as temporary:
        settings = AppSettings(APP_ENV="test", APP_DEBUG=False, DATABASE_URL=f"sqlite:///{temporary}/demo.db",
                               ARTIFACTS_ROOT=temporary, LEGACY_APP_ROOT=Path(__file__).resolve().parents[1]/"legacy_runtime",
                               CACHE_MODE="off", NEO_LLM_BUDGET_USD="2")
        if not provisional and not settings.openrouter_api_key:
            raise SystemExit("BLOCKER: OPENROUTER_API_KEY is unavailable. From apps/api run: python scripts/make_demo_fixtures.py with the API settings configured.")
        if provisional:
            settings.openrouter_api_key = "provisional-no-network"
        capped = CappedProvider(service._call_openrouter_messages)
        original = service._call_openrouter_messages
        service._call_openrouter_messages = provisional_provider if provisional else capped
        engine = create_engine(settings.database_url)
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                db.add_all(Persona(**row) for row in load_persona_seed_rows())
                study = Study(public_id="demo-fixture-builder", lifecycle_status="active")
                db.add(study)
                db.commit()
                ids = [f"P{i:03}" for i in range(1, 7)]
                room = fg.start_room(db, settings, study, {"request_id": str(uuid4()), "persona_ids": ids, "model": MODEL, "max_rounds": 8})
                rounds = [
                    ("icebreaker", "Who lives with you and what does a weekday look like?", {}),
                    ("space_needs", "Where do you run out of space at home?", {}),
                    ("space_needs", "What makes that situation difficult for you?", {"recipients": ids[:1]}),
                    ("concept", fg.CONCEPT_CARD["introduction"], {"reveal": "concept"}),
                    ("price_reactions", "What would you expect something like this to cost?", {}),
                    ("price_reactions", "At about $23,000, how does your reaction change?", {"reveal": "price"}),
                    ("close", "What else should we have asked?", {}),
                ]
                for stage, question, extra in rounds:
                    room = fg.ask_round(db, settings, study, room["room_id"], {"revision": room["revision"], "stage": stage, "question": question, **extra})
                    if room["status"] not in {"running", "completed"}:
                        raise RuntimeError("Focus group fixture failed; no files written")
                batch = si.start_batch(db, settings, study, {"request_id": str(uuid4()), "persona_count": 6,
                    "interviewer_model": MODEL, "interviewee_model": MODEL})
                for _ in range(96):
                    batch = si.advance_batch(db, settings, study, batch["job_id"], {"revision": batch["revision"]})
                    if batch["status"] not in {"running", "completed"}:
                        raise RuntimeError("Batch fixture failed; no files written")
                assert batch["status"] == "completed"
                messages, session_id = [], None
                for answer in ANSWERS:
                    question = si.next_human_question(db, settings, study, {"session_id": session_id, "messages": messages})
                    session_id = question["session_id"]
                    messages.extend([{"role": "user", "content": question["question"]}, {"role": "assistant", "content": answer}])
                fixtures = {}
                for kind, public_id in [("focus-group", room["room_id"]), ("batch", batch["job_id"])]:
                    job = db.scalar(select(Job).where(Job.public_id == public_id))
                    config = deepcopy(job.payload_json)
                    if kind == "focus-group":
                        config["demo_cards"] = {pid: persona_cards()[pid] for pid in ids}
                    fixtures[kind] = {"config": config, "state": deepcopy(job.result_json)}
                fixtures["you"] = {"config": {}, "state": {"messages": messages, "model": question["interviewer_model"]}}
                OUTPUT.mkdir(parents=True, exist_ok=True)
                for kind, data in fixtures.items():
                    data.update(kind=kind, provisional=provisional, source="hand-written" if provisional else "real-service-model-run",
                                generation={"script": "scripts/make_demo_fixtures.py", "cost_usd": str(capped.measured),
                                            "reserved_usd": str(capped.reserved), "calls": capped.calls, "limit_usd": "2"})
                    (OUTPUT / f"{kind}.json").write_text(json.dumps(data, indent=2) + "\n")
                print("Wrote three", "provisional hand-written" if provisional else "real model", "fixtures; measured cost", capped.measured)
        finally:
            service._call_openrouter_messages = original
            engine.dispose()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provisional", action="store_true")
    build(parser.parse_args().provisional)
