"""Simulated focus group: one student moderator, several personas reacting to each other.

Its own lane. Rooms are `focus_group_room` jobs, so nothing here appears in the
interview section's batch lists, the standalone themes input, or the pre-recorded
interviews page — all of which select on their own job_type.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from copy import deepcopy
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from src.persistence.models import InterviewTurn, Job, Persona
from src.services.exceptions import (ApiError, ConflictApiError, NotFoundApiError,
    ProviderUnavailableApiError, QuotaExceededApiError, TransientProviderError, ValidationApiError)
from src.services.interview_cache import resolve_interview_answer
from src.services.llm_budget import (enforce_budget_open, enforce_measured_cost, enforce_run_preflight,
    load_interview_budget_snapshot, lock_class_budget_for_transaction)
from src.services.model_catalog import list_interview_model_catalog
from src.services.standalone_interview import serialized_local, usage, validate_models

logger = logging.getLogger(__name__)

JOB_TYPE = "focus_group_room"

# The PA3.5 funnel, in order. Price is the fourth stop on purpose: "don't anchor first".
STAGES = ("icebreaker", "space_needs", "concept", "price_reactions", "close")
STAGE_LABELS = {
    "icebreaker": "Icebreaker",
    "space_needs": "General space needs",
    "concept": "The Tahoe Mini concept",
    "price_reactions": "Price reactions",
    "close": "Close",
}

MIN_PERSONAS = 3          # Lin: "3 is the floor — a group, not an interview"
MAX_PERSONAS = 8
MAX_ROUNDS = 12
# Lin fix 4: five core questions (one per stage) plus three follow-up probes by default.
CORE_QUESTIONS = 5
DEFAULT_ROUNDS = CORE_QUESTIONS + 3
MAX_EXTENSION_ROUNDS = 4
PROVIDER_TIMEOUT_SECONDS = 60

# Planning allowance for ONE persona turn in a room (the transcript is resent each
# round, so the prompt is larger than a single chat turn and smaller than a full
# AI-to-AI interview). Mirrored in apps/web/src/lib/focus-group.ts so the pre-start
# estimate the student approves is the number the server bills against; a test pins
# the two copies together.
ESTIMATED_PROMPT_TOKENS_PER_TURN = 2_000
ESTIMATED_COMPLETION_TOKENS_PER_TURN = 400
_TOKENS_PER_MILLION = Decimal("1000000")

# A memo needs enough room to stand on: both product stages reached, and enough
# answered turns that themes/surprise/options are read rather than invented. The floor
# is the smallest clean room that reaches price — MIN_PERSONAS through the first four
# stages — so a room that got there with holes in it is refused rather than padded.
MEMO_REQUIRED_STAGES = ("concept", "price_reactions")
MEMO_MIN_ANSWERS = MIN_PERSONAS * (STAGES.index("price_reactions") + 1)
MEMO_MODEL = "openai/gpt-4o-mini"
MEMO_MIN_THEMES, MEMO_MAX_THEMES = 3, 6
MEMO_MIN_ANSWER_OPTIONS = 3

# Lin: every output says what it is. Plain ASCII so it survives CSV and copy/paste.
REHEARSAL_LABEL = "Synthetic rehearsal - not PA3.5 live fieldwork"

# The instructor-approved concept card. The page renders it above the question field,
# the student can copy it into ChatGPT, and CONCEPT_STIMULUS — its plain-text form — is
# exactly what participants are given once the moderator introduces it. One source, so
# "what the student showed" and "what the model was told" cannot drift apart.
CONCEPT_CARD = {
    "name": "Tahoe Mini by Neo Smart Living",
    "description": ("A compact 117-square-foot factory-built studio that is delivered and installed "
                    "in a backyard. It is not an ADU and has no kitchen or bathroom."),
    "specs": ["117 square feet", "Factory-built; delivered and installed in your backyard",
              "Not an ADU: no kitchen, no bathroom"],
    "intended_for": "homeowners with usable outdoor space",
    "introduction": ("I'd like to show you an idea. It's called the Tahoe Mini, from Neo Smart Living: "
                     "a compact 117-square-foot studio, built in a factory, then delivered and installed "
                     "in your backyard. It isn't an ADU, so there's no kitchen or bathroom. "
                     "What's your first reaction, and what would you use it for?"),
}
CONCEPT_STIMULUS = "\n".join([
    "PRODUCT CONCEPT SHOWN BY THE MODERATOR:",
    f"Name: {CONCEPT_CARD['name']}",
    f"Description: {CONCEPT_CARD['description']}",
    *(f"- {spec}" for spec in CONCEPT_CARD["specs"]),
    f"Intended for: {CONCEPT_CARD['intended_for']}",
])
# Withheld from every participant prompt until the moderator's explicit Reveal price.
PRICE = "about $23,000"
PRICE_STIMULUS = f"PRICE SHOWN BY THE MODERATOR: {PRICE}"
STIMULI = {"concept": CONCEPT_STIMULUS, "price": PRICE_STIMULUS}

# Rounds stored before the reveal controls existed (rooms run in class on 2026-09-23) carry
# no "kind" and no "stimulus", but the old stage map still put the concept into every prompt
# from the concept stage on, and the price from price_reactions on. Read as absent, those
# rooms would claim participants were never shown what they discussed (refuter
# LEGACY-STIMULUS / SOL-1), so the exposure is derived from the stage, with the old text.
_LEGACY_CONCEPT = """PRODUCT BEING DISCUSSED:
Name: Tahoe Mini by Neo Smart Living
Description: A compact 117-square-foot factory-built studio that is delivered and installed in a backyard. It is not an ADU and has no kitchen or bathroom.
Intended for: homeowners with usable outdoor space"""
_LEGACY_STIMULI = (("concept", "concept", _LEGACY_CONCEPT), ("price", "price_reactions", f"Price: {PRICE}"))


def with_legacy_stimuli(rounds):
    """Rounds with the stage-implied stimulus on the legacy round that first showed it.

    ponytail: one stimulus per round. The old funnel refused price_reactions until a concept
    round was answered, so a legacy round never introduced both; if one somehow did, the
    concept is attached and the price lands on the next legacy round at price or later."""
    shown = {r["stimulus"]["kind"] for r in rounds if r.get("stimulus")}
    out = []
    for r in rounds:
        if "kind" not in r and not r.get("stimulus"):
            for kind, stage, text in _LEGACY_STIMULI:
                if kind not in shown and STAGES.index(r["stage"]) >= STAGES.index(stage):
                    r = {**r, "stimulus": {"kind": kind, "text": text, "derived": True}}
                    shown.add(kind)
                    break
        out.append(r)
    return out


def _normalized(state):
    return {**state, "rounds": with_legacy_stimuli(state.get("rounds", []))}


def _shown(rounds):
    return {r["stimulus"]["kind"] for r in rounds if r.get("stimulus")}


def _counted(rounds):
    """Rounds that count toward reaching their stage. A question at the concept stage asked
    without the concept on screen did not reach the concept stage (refuter
    CONCEPT-STAGE-REACHED-WITHOUT-CONCEPT), so it neither advances the funnel nor makes the
    memo eligible."""
    concept_shown, out = False, []
    for r in rounds:
        concept_shown = concept_shown or (r.get("stimulus") or {}).get("kind") == "concept"
        if concept_shown or STAGES.index(r["stage"]) < STAGES.index("concept"):
            out.append(r)
    return out

# A moderator question that names a dollar figure before the price is revealed anchors the
# room just as surely as the app doing it. Refuse it and say why.
# A dollar sign, a thousands-grouped figure, or a bare number carrying a money word.
# A bare four-digit integer alone is a year far more often than a price ("in 2026",
# "since 1990"), and refusing those blocked legitimate pre-price questions (refuter FG-G).
_MONEY = re.compile(r"\$\s*\d|\b\d{1,3},\d{3}\b"
                    r"|\b\d{3,}\s*(?:dollars|usd|bucks|k\b)|\b(?:dollars|usd|price|cost)\b[^.?!]{0,20}\b\d{3,}\b",
                    re.I)


# Personas that all see each other's answers converge on agreement. That is documented
# group conformity in multi-agent LLM systems, attributed to RLHF optimizing for
# agreeableness, and the literature reports it is tunable through PERSONA rather than
# through information framing (Findings of ACL 2025; arXiv 2405.03862). So the room is
# seeded with differing dispositions instead of hiding what each participant sees:
# mutual visibility IS the focus group, and withholding it would leave parallel
# interviews. A stance is a disposition, never a rewrite of who the persona is — the
# Census-drawn profile still decides the facts of their life.
_STANCES = (
    "You are the room's skeptic. Assume the product is overpromised until someone gives you a"
    " concrete reason otherwise, and say plainly when an answer has not convinced you.",
    "You are the most willing person in the room. When others hesitate, say so and make the case"
    " for trying it anyway.",
    "You judge everything by whether it fits the routine you already have. Abstract benefits do"
    " not move you; describe the specific moment in your day it would or would not fit.",
    "Value for money is your lens before anything else. Keep returning to what it costs against"
    " what you would actually get.",
    "You do not trust connected devices or the companies behind them with what happens in your"
    " home. Raise that even when nobody else in the room has.",
    "You expect things like this to end up unused after a month. Say what would have to be true"
    " for that not to happen, without claiming purchases your life has not actually included.",
    "You answer for your household before yourself. Keep asking how this would land for the other"
    " people you live with, not only for you.",
    "You believe it when you see it fail well. Ask what happens when it breaks, and say what would"
    " have to go wrong for you to walk away.",
)

# A room may seat up to MAX_PERSONAS, and the whole point is that no two seats share a
# disposition, so the list has to cover the largest legal room.
assert len(_STANCES) >= MAX_PERSONAS, "every seat in a full room needs its own stance"


# _STANCES are dispositions toward the product, so they cannot appear before the product
# does. That gate (below) is right, but it leaves icebreaker and space_needs with nothing
# steering HOW a seat talks: the prompts differ by persona (id and description), yet none of
# them asks for a distinct voice, so a room of five answers the first two questions in one
# register. A manner is about how a person talks, not what they think of anything, so it
# carries no product awareness and is safe at every stage.
_MANNERS = (
    "You answer briefly. Two or three sentences and you are done; you do not pad with"
    " background nobody asked for.",
    "You think out loud and reach your point late. Start with the specific thing that"
    " happened recently, then say what it means.",
    "You qualify almost everything -- 'it depends', 'usually', 'I guess'. Stating something"
    " flatly makes you uncomfortable when the real answer varies.",
    "You state things flatly and do not hedge. If you are unsure you say so outright, but you"
    " never soften the part you do know.",
    "You are the one who disagrees. When the room converges, look for what nobody said and"
    " name where your own experience does not match theirs.",
    "You reach for concrete numbers and times -- how many minutes, how many times a week --"
    " instead of calling something 'a lot' or 'a while'.",
    "You volunteer more than was asked: a side story, an aside about someone else, the thing"
    " it reminds you of.",
    "You answer narrowly and literally. Respond to the question that was actually asked and"
    " do not extend it.",
)

# A student persona's optional conversation style, as a manner.
_STYLE_MANNERS = {"brief": _MANNERS[0], "talkative": _MANNERS[6]}

# Same rule as _STANCES: no two seats in a full room share one.
assert len(_MANNERS) >= MAX_PERSONAS, "every seat in a full room needs its own manner"


def _seat_pick(options, persona_ids, persona_id: str) -> str:
    """Give each seat its own entry from options, deterministically.

    The modulo never actually wraps — the asserts above keep every list at least
    MAX_PERSONAS long — it is there so a larger room degrades to a repeat rather
    than an IndexError mid-answer.
    """
    seats = list(persona_ids)
    # The roster is what builds the answer rows, so a persona is always on it. Falling
    # back to the first seat keeps a malformed room answering rather than raising mid-turn.
    seat = seats.index(persona_id) if persona_id in seats else 0
    return options[seat % len(options)]


def room_stance(persona_ids, persona_id: str) -> str:
    """One disposition per seat, so a room of N draws N different stances."""
    return _seat_pick(_STANCES, persona_ids, persona_id)


def room_manner(persona_ids, persona_id: str) -> str:
    """One speaking manner per seat, drawn the same way a stance is.

    Kept separate from room_stance because the two answer different questions: a stance is
    what this person thinks of the product, a manner is how they talk at all. Only the
    second one is safe before the product has been introduced.
    """
    return _seat_pick(_MANNERS, persona_ids, persona_id)


def persona_description(profile: dict) -> str:
    from src.services.interview_service import build_persona_description
    return build_persona_description(profile)


def shared_stimuli(rounds, upto_index):
    """Everything participants have been shown by the time round `upto_index` is asked."""
    return [r["stimulus"] for r in rounds[:upto_index + 1] if r.get("stimulus")]


def build_room_system_prompt(profile: dict, shared=(), stance: str = "", manner: str = "",
                             description: str | None = None) -> str:
    """`shared` is the list of stimuli the moderator has released, in order. Nothing
    about the product reaches a participant any other way."""
    kinds = {item["kind"] for item in shared}
    if shared:
        shown = "\n\n".join(item["text"] for item in shared)
        product = f"\nWHAT THE MODERATOR HAS SHOWN YOU SO FAR:\n{shown}\n"
    else:
        product = ("\nWHAT THE MODERATOR HAS SHOWN YOU SO FAR:\nNothing about any product. You know only "
                   "what has been said out loud in this room.\n")
    # Pre-exposure rounds get no stance. Every disposition below is about the product,
    # and a persona already skeptical of it is a persona who knows it exists
    # (refuter FG-STANCE-2). The gate is the concept having been shown, not the stage.
    stance_block = f"\nYOUR STANCE GOING IN:\n{stance}\n" if stance and "concept" in kinds else ""
    # A manner carries no product awareness, so unlike a stance it is not gated.
    manner_block = f"\nHOW YOU TALK:\n{manner}\n" if manner else ""
    price_rule = "" if "price" in kinds else (
        "\n- No price has been shown to you. If asked what it would or should cost, give your own"
        "\n  guess and say it is a guess; never state a figure as the product's actual price.")
    return f"""You are role-playing as a real person taking part in a moderated focus group with other participants.

You are participant {profile.get('persona_id', 'unknown')} in this room.

YOUR PERSONA:
{description if description is not None else persona_description(profile)}
{product}{stance_block}{manner_block}
INSTRUCTIONS:
- Stay fully in character. Answer the moderator as this person would, in first person.
- Never mention being an AI, a model, a simulation, a prompt or instructions — not even to
  explain why you are quiet. If the moderator addresses someone else, that question is not for you.
- You know only what is listed above and what was said in the room. Do not invent product
  details (size, features, amenities, price) you were not shown.{price_rule}
- This is a group, not an interview. Whenever other participants' answers are shown to you,
  respond to at least one of them BY NAME before or while answering the moderator — agree,
  push back, or add the thing they left out. "P002 said X, but for me..." is the shape.
  Do not restate the room's consensus; say where you differ.
- Be specific and personal. Real trade-offs, not marketing-speak.
- Do NOT prefix your answer with your own participant id — the transcript already attributes you.
- Keep it conversational, two to five sentences, plain prose."""


def estimate_room_cost_usd(*, persona_count: int, rounds: int, model_id: str) -> Decimal:
    model = next(m for m in list_interview_model_catalog()["models"] if m["id"] == model_id)
    per_turn = (Decimal(str(model["prompt_price_per_million"])) * ESTIMATED_PROMPT_TOKENS_PER_TURN
                + Decimal(str(model["completion_price_per_million"])) * ESTIMATED_COMPLETION_TOKENS_PER_TURN)
    return (per_turn * persona_count * rounds) / _TOKENS_PER_MILLION


def participant_card(config, persona_id):
    if config.get("demo_cards", {}).get(persona_id):
        return config["demo_cards"][persona_id]
    custom = config.get("custom_personas", {}).get(persona_id)
    if custom:
        return custom["card"]
    from src.persistence.persona_seed import persona_cards
    return persona_cards().get(persona_id)


def owned_room(session, study, room_id, *, lock=False):
    query = select(Job).where(Job.public_id == room_id, Job.study_id == study.id, Job.job_type == JOB_TYPE)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    room = session.scalar(query)
    if not room or room.status == "deleted":
        raise NotFoundApiError("Focus group room not found.")
    return room


def _answered(state):
    return [(r, a) for r in state["rounds"] for a in r["answers"] if a["status"] == "answered"]


def turn_id(round_index, persona_id=None):
    """A turn's stable ID. Rounds are append-only and a persona holds one seat, so the
    round number and the speaker name a turn for the life of the room — retries and
    later rounds never renumber it."""
    return f"R{round_index + 1}-{persona_id or 'MOD'}"


def _with_turn_ids(rounds):
    return [{**r, "turn_id": turn_id(r["index"]),
             "answers": [{**a, "turn_id": turn_id(r["index"], a["persona_id"])} for a in r["answers"]]}
            for r in rounds]


def room_status(session, settings, study, room_id, room=None):
    room = room or owned_room(session, study, room_id)
    state = _normalized(room.result_json or {})
    config = room.payload_json or {}
    stages_reached = sorted({r["stage"] for r in _counted(state["rounds"]) if
                             any(a["status"] == "answered" for a in r["answers"])}, key=STAGES.index)
    return {
        "room_id": room.public_id,
        "status": room.status,
        **room.payload_json,
        **state,
        # Derived on read, never stored: a room written before turn IDs existed gets the
        # same IDs a new one does.
        "rounds": _with_turn_ids(state["rounds"]),
        "manual_memo_check": manual_memo_check(state),
        "allowance": allowance(config, state),
        # .get with start_room's defaults: a room row missing a key, or whose model has since
        # left the catalog, must still open and export (refuter SOL-4).
        "estimated_total_cost_usd": str(Decimal(config.get("estimated_cost_usd") or "0") + sum(
            (Decimal(e["estimated_cost_usd"]) for e in state.get("extensions", [])), Decimal("0"))),
        "extension_cost_per_round_usd": _extension_cost(config),
        "rehearsal_label": REHEARSAL_LABEL,
        # The moderator sees the price; participants do not until it is revealed.
        "concept_card": {**CONCEPT_CARD, "text": CONCEPT_STIMULUS, "price": PRICE},
        "shared": shared_view(state.get("rounds", [])),
        # The same cards the student recruited from, so they can be reopened mid-discussion.
        "participants": [{"persona_id": pid, "card": participant_card(room.payload_json, pid)}
                         for pid in config.get("persona_ids", [])],
        "stage": STAGES[state.get("stage_index", 0)],
        "stages": list(STAGES),
        "stage_labels": STAGE_LABELS,
        "stages_reached": stages_reached,
        "complete": room.status == "completed" and not _missing(state),
        "error": room.error_json,
        "session_usage": usage(session, settings, room.public_id),
    }


def _extension_cost(config):
    try:
        return str(estimate_room_cost_usd(persona_count=len(config.get("persona_ids", [])), rounds=1,
                                          model_id=config.get("model")))
    except StopIteration:
        return None  # the model is no longer offered, so neither is an extension


def list_rooms(session, settings, study):
    rooms = session.scalars(select(Job).where(
        Job.study_id == study.id, Job.job_type == JOB_TYPE, Job.status != "deleted"
    ).order_by(Job.queued_at.desc())).all()
    return [room_status(session, settings, study, room.public_id, room=room) for room in rooms]


@serialized_local
def delete_room(session, study, room_id):
    room = owned_room(session, study, room_id, lock=True)
    # ponytail: tombstone, not a row delete. The room's InterviewTurn cost rows stay —
    # deleting them would let a student clear their own spend against the class budget.
    room.status = "deleted"
    session.commit()
    return {"room_id": room_id, "deleted": True}


@serialized_local
def start_room(session, settings, study, payload):
    from src.services.interview_service import utcnow
    persona_ids = payload.get("persona_ids")
    if not isinstance(persona_ids, list) or any(not isinstance(p, str) for p in persona_ids):
        raise ValidationApiError("Choose the personas for the room.")
    if len(persona_ids) != len(set(persona_ids)):
        raise ValidationApiError("Each persona can only take one seat in the room.")
    if len(persona_ids) < MIN_PERSONAS:
        raise ValidationApiError(
            f"A focus group needs at least {MIN_PERSONAS} personas — fewer than that is an interview, not a group.")
    if len(persona_ids) > MAX_PERSONAS:
        raise ValidationApiError(f"A room holds at most {MAX_PERSONAS} personas.")
    rounds = payload.get("max_rounds", DEFAULT_ROUNDS)
    if type(rounds) is not int or not 1 <= rounds <= MAX_ROUNDS:
        raise ValidationApiError(f"Plan between 1 and {MAX_ROUNDS} questions for the room.")
    model = payload.get("model")
    validate_models([model], payload.get("allow_expensive_models"))
    from src.services.focus_group_personas import frozen_seats, is_student_persona_id
    roster_ids = [pid for pid in persona_ids if not is_student_persona_id(pid)]
    found = session.scalars(select(Persona).where(Persona.persona_id.in_(roster_ids))).all()
    if len(found) != len(roster_ids):
        raise ValidationApiError("One or more of the selected personas is unavailable.")
    # Student personas are frozen into the room at the version seated (Lin fix 3).
    custom = frozen_seats(session, study, persona_ids)
    try:
        request_id = str(UUID(str(payload.get("request_id"))))
    except ValueError as exc:
        raise ValidationApiError("request_id must be a UUID.") from exc
    room_id = "fg_" + hashlib.sha256(f"{study.id}:{request_id}".encode()).hexdigest()[:40]
    from src.services.interview_cache import _lock_cache_key_for_transaction
    _lock_cache_key_for_transaction(session, hashlib.sha256(room_id.encode()).hexdigest())
    config = {"persona_ids": persona_ids, "model": model, "max_rounds": rounds,
              "estimated_cost_usd": str(estimate_room_cost_usd(
                  persona_count=len(persona_ids), rounds=rounds, model_id=model)),
              **({"custom_personas": custom} if custom else {})}
    existing = session.scalar(select(Job).where(Job.public_id == room_id))
    if existing:
        # A double-clicked start, or a lost creation response, resolves to the one room.
        if existing.payload_json != config:
            raise ConflictApiError("This room request ID was already used with different settings.")
        return room_status(session, settings, study, room_id)
    room = Job(public_id=room_id, study_id=study.id, job_type=JOB_TYPE, status="running",
               payload_json=config, result_json={"revision": 0, "stage_index": 0, "rounds": [], "memo": None},
               queued_at=utcnow(), started_at=utcnow())
    session.add(room)
    session.commit()
    return room_status(session, settings, study, room_id)


@serialized_local
def cancel_room(session, settings, study, room_id):
    room = owned_room(session, study, room_id, lock=True)
    if room.status in {"running", "failed", "budget_stopped"}:
        room.status = "cancelled"
        # Already-charged answers stay exactly where they are; no further paid call
        # can be made against a cancelled room.
        session.commit()
    return room_status(session, settings, study, room_id)


def _missing(state):
    # "silent" is a participant the question was not addressed to: intended, not a hole.
    return [(r["index"], a["persona_id"]) for r in state.get("rounds", [])
            for a in r["answers"] if a["status"] == "missing"]


def _moderator_line(round_):
    to = round_.get("recipients")
    return f"Moderator (to {', '.join(to)}): {round_['question']}" if to else f"Moderator: {round_['question']}"


# A participant talking about being an AI, its prompt or its instructions is out of
# character — the "P002 only" failure Lin saw. Such a reply never enters the dialogue.
# Only SELF-reference counts: "as an AI," / "I'm an AI language model" / "my instructions" /
# "system prompt". A persona who works on "a large language model at my job" or is "an AI
# researcher" is in character (refuter OOC-REGEX-REPEAT-CHARGE), so a bare "AI" must end the
# clause or be followed by model/assistant/chatbot.
# ponytail: a phrase list, not a classifier; a subtler slip gets through. Upgrade to a judged
# check if the logs show misses.
_SELF_AI = (r"(?:(?:ai|artificial intelligence) (?:language model|model|assistant|chatbot)\b"
            r"|(?:(?:large )?language model|chatbot|ai|artificial intelligence)(?=\s*(?:[.,;:!?]|$)))")
_OUT_OF_CHARACTER = re.compile(
    rf"\b(?:as an? {_SELF_AI}|i(?:'|’)?m (?:just |only |not )?an? {_SELF_AI}|i am (?:just |only |not )?an? {_SELF_AI}"
    r"|my (?:system )?instructions\b|system prompt\b|i(?:'|’)?m (?:just )?role-?playing\b|i am (?:just )?role-?playing\b"
    r"|simulated (?:persona|participant|focus group)\b)", re.I | re.M)


def out_of_character(text):
    return bool(_OUT_OF_CHARACTER.search(text or ""))


OUT_OF_CHARACTER_MESSAGE = ("The reply stepped out of character, so it was kept out of the "
                            "discussion. Retry this turn.")


class OutOfCharacterReply(TransientProviderError):
    """A billed reply withheld for breaking character. Its own type, so the error code never
    depends on a message string surviving a wrapper (refuter SOL-3). Raised once per call:
    the provider is asked with max_attempts=1 and nothing retries it automatically, so a
    flagged turn costs one charge per student click."""


def allowance(config, state):
    """Core questions are one per stage and are reserved: a probe may never spend the
    question a stage still needs, so a room can always reach its close."""
    total = config.get("max_rounds", MAX_ROUNDS) + state.get("extra_rounds", 0)
    rounds = with_legacy_stimuli(state.get("rounds", []))
    asked_stages = {r["stage"] for r in _counted(rounds)}
    cores_left = len([s for s in STAGES if s not in asked_stages])
    probes_used = sum(1 for r in rounds if r.get("kind") == "probe")
    return {"total": total, "used": len(rounds), "cores_total": CORE_QUESTIONS,
            "cores_left": cores_left, "probes_used": probes_used,
            "probes_left": max(total - len(rounds) - cores_left, 0),
            "extensions_left": MAX_EXTENSION_ROUNDS - state.get("extra_rounds", 0)}


def _prior_messages(state, persona_id):
    """What this persona has seen: its own earlier answers, plus what the others said.

    Earlier ROUNDS only. Within a round every persona answers the same question from
    the same context, so no persona ever sees its own future turns and the room does
    not depend on the order the personas happened to be called in.
    """
    messages = []
    for round_ in state["rounds"]:
        answers = {a["persona_id"]: a for a in round_["answers"] if a["status"] == "answered"}
        if not answers:
            continue
        messages.append({"role": "user", "content": _moderator_line(round_)})
        own = answers.get(persona_id)
        if own:
            messages.append({"role": "assistant", "content": own["text"]})
        others = [f"- {pid}: {answer['text']}" for pid, answer in answers.items() if pid != persona_id]
        if others:
            messages.append({"role": "user", "content": "In the room, the other participants answered:\n"
                             + "\n".join(others)})
    return messages


@serialized_local
def ask_round(session, settings, study, room_id, payload):
    """One moderator question -> one answer per persona, each separately budgeted.

    Exactly one accepted call per revision: a resubmitted or double-clicked revision
    returns the current room and spends nothing.
    """
    from src.services import interview_service as service
    room = owned_room(session, study, room_id, lock=True)
    from src.services.demo_mode import refuse_demo
    refuse_demo(room)
    if type(payload.get("revision")) is not int:
        raise ValidationApiError("An integer room revision is required.")
    if room.status in {"cancelled", "completed"}:
        raise ConflictApiError(f"This room is {room.status}; its transcript stays readable.")
    state = _normalized(deepcopy(room.result_json))
    if payload["revision"] != state["revision"]:
        # Stale revision: a second submit while the first round was still generating,
        # or a retried request whose first attempt already landed.
        return room_status(session, settings, study, room_id)
    retry = payload.get("retry") is True
    if retry:
        if not _missing(state):
            return room_status(session, settings, study, room_id)
        targets = [r for r in state["rounds"] if any(a["status"] == "missing" for a in r["answers"])]
        stage = targets[-1]["stage"]
    else:
        stage = str(payload.get("stage") or STAGES[state["stage_index"]])
        if stage not in STAGES:
            raise ValidationApiError("Unknown focus-group stage.")
        reached = {r["stage"] for r in _counted(state["rounds"])
                   if any(a["status"] == "answered" for a in r["answers"])}
        furthest = max((STAGES.index(s) for s in reached), default=-1)
        if STAGES.index(stage) > furthest + 1:
            # "Work the funnel in order" is the wrong sentence when the funnel WAS worked in
            # order and the provider simply never answered: a round whose every answer failed
            # leaves furthest where it was, and the student got told about ordering when the
            # real state is an unanswered round to retry. Say which it is.
            unanswered = [r for r in state["rounds"]
                          if not any(a["status"] == "answered" for a in r["answers"])]
            if unanswered:
                last = unanswered[-1]
                raise ValidationApiError(
                    f"No one answered your {STAGE_LABELS[last['stage']]} question yet, so the room "
                    f"cannot move on. Retry that round first.")
            raise ValidationApiError(
                f"Work the funnel in order: {STAGE_LABELS[STAGES[furthest + 1]]} comes before "
                f"{STAGE_LABELS[stage]}.")
        reveal = payload.get("reveal")
        shown = _shown(state["rounds"])
        # A concept-stage question without the concept on screen is not the stage's core
        # question: it spends a probe, so it can never use up the question the funnel needs.
        counts = STAGES.index(stage) < STAGES.index("concept") or "concept" in shown or reveal == "concept"
        kind = "core" if counts and all(r["stage"] != stage for r in _counted(state["rounds"])) else "probe"
        left = allowance(room.payload_json, state)
        if left["used"] >= left["total"]:
            raise ValidationApiError("This room has used all the questions it was started with.")
        if kind == "probe" and left["probes_left"] <= 0:
            raise ValidationApiError(
                ("" if counts else "Introduce the concept with this question — without it, the question "
                 "does not count as the concept stage. ")
                + f"No follow-up probes left: the remaining {left['cores_left']} question(s) are held for "
                "the stages you have not asked yet. Move to the next stage, or extend the room for "
                "more probes.")
        recipients = _check_recipients(room.payload_json["persona_ids"], payload.get("recipients"))
        question = str(payload.get("question") or "").strip()
        if not question:
            raise ValidationApiError("Type the question you want to put to the room.")
        _check_reveal(state, stage, reveal)
        if "price" not in shown and reveal != "price" and _MONEY.search(question):
            raise ValidationApiError(
                "Don't anchor price first — ask the unaided price question, then use Reveal price "
                "before naming a dollar figure.")
        photo = _check_photo(payload.get("photo"), reveal, "price" in shown)
        # Going back to an early stage is allowed, but once anything was shown the room
        # has seen it, so the round is recorded as what it is and the export cannot
        # present it as pre-exposure data (refuter FG-C).
        post_exposure = STAGES.index(stage) < STAGES.index("concept") and bool(shown)
        round_ = {"index": len(state["rounds"]), "stage": stage, "question": question,
                  "post_exposure": post_exposure, "kind": kind, "recipients": recipients,
                  **({"stimulus": {"kind": reveal, "text": _stimulus_text(reveal, photo),
                                   **({"photo": photo} if photo else {})}} if reveal else {}),
                  "answers": [{"persona_id": pid, "text": "",
                               "status": "missing" if not recipients or pid in recipients else "silent",
                               "error": None}
                              for pid in room.payload_json["persona_ids"]]}
        state["rounds"].append(round_)
        targets = [round_]
    model = room.payload_json["model"]
    stopped = None
    charged_any = False

    def run_answer(round_, answer, history):
        """One persona's turn: budgeted, cached, charged, and recorded on its own."""
        nonlocal charged_any
        stage_ = round_["stage"]
        seats = room.payload_json["persona_ids"]
        stance = room_stance(seats, answer["persona_id"])
        manner = room_manner(seats, answer["persona_id"])
        custom = room.payload_json.get("custom_personas", {}).get(answer["persona_id"])
        if custom:
            # The frozen snapshot, never the live persona: edits after the start do not
            # reach a running room. A chosen style replaces the seat's drawn manner.
            profile, description = {"persona_id": answer["persona_id"]}, custom["description"]
            manner = _STYLE_MANNERS.get(custom["style"], manner)
        else:
            profile, description = session.get(Persona, answer["persona_id"]).profile_json, None
        prior = [{"role": "system",
                  "content": build_room_system_prompt(
                      profile, shared_stimuli(state["rounds"], round_["index"]), stance, manner,
                      description=description)},
                 *_prior_messages(history, answer["persona_id"])]
        question_text = _moderator_line(round_)
        budget_error = None

        def provider():
            nonlocal budget_error
            lock_class_budget_for_transaction(session)
            snapshot = load_interview_budget_snapshot(session, session_id=room_id,
                                                      run_budget_usd=settings.llm_budget_usd)
            enforce_budget_open(snapshot)
            if snapshot.run_provider_call_count == 0:
                enforce_run_preflight(estimated_cost_usd=room.payload_json["estimated_cost_usd"],
                                      class_spent_usd=snapshot.class_spent_usd,
                                      run_budget_usd=snapshot.run_budget_usd)
            if not settings.openrouter_api_key:
                raise ConflictApiError("OPENROUTER_API_KEY is not configured.")
            result = service._call_openrouter_messages(
                api_key=settings.openrouter_api_key or "", model=model,
                messages=[*prior, {"role": "user", "content": question_text}],
                timeout=PROVIDER_TIMEOUT_SECONDS, max_attempts=1)
            try:
                enforce_measured_cost(snapshot, cost_usd=result.cost_usd)
            except QuotaExceededApiError as exc:
                budget_error = exc
            if out_of_character(result.text):
                # Raised, not returned: a billed reply is still recorded, and it never
                # reaches the answer cache, so a retry asks again instead of replaying it.
                raise OutOfCharacterReply(OUT_OF_CHARACTER_MESSAGE, measured_usage=result)
            return result

        def log(error):
            logger.warning("focus_group_failure room=%s stage=%s persona=%s model=%s code=%s error=%s",
                           room_id, stage_, answer["persona_id"], model, error.code, error.message)

        try:
            reply = resolve_interview_answer(session, cache_mode=settings.cache_mode,
                persona_id=answer["persona_id"], model=model, question=question_text,
                prior_turns=prior, call_provider=provider)
        except Exception as exc:
            measured = exc.measured_usage if isinstance(exc, TransientProviderError) else None
            if measured is not None:
                _record_usage(session, study, room_id, answer["persona_id"], measured)
                charged_any = True
            error = exc if isinstance(exc, ApiError) else ProviderUnavailableApiError(str(exc))
            if isinstance(exc, OutOfCharacterReply):
                error.code = "out_of_character"
            answer["error"] = {"code": error.code, "message": error.message}
            log(error)
            # A budget stop ends the room's spending; one persona failing only leaves a
            # visible hole, so the personas after it still get their turn.
            if isinstance(exc, QuotaExceededApiError):
                return exc
            return budget_error  # an out-of-character reply can still be the one that hit the cap
        _record_usage(session, study, room_id, answer["persona_id"], reply)
        charged_any = charged_any or reply.cost_usd > 0
        if out_of_character(reply.text):  # an answer cached before this guard existed
            answer["error"] = {"code": "out_of_character", "message": OUT_OF_CHARACTER_MESSAGE}
            return budget_error
        answer.update(text=reply.text, status="answered", error=None)
        if budget_error is not None:
            log(budget_error)
        return budget_error

    for round_ in targets:
        # Prior context is read from the rounds BEFORE this one, so a retry rebuilds the
        # same prompts the first attempt used and lands on the same cache keys.
        history = {"rounds": state["rounds"][:round_["index"]]}
        for answer in round_["answers"]:
            if answer["status"] != "missing":
                continue  # A retry re-runs only the turns that are actually missing; silent stays silent.
            stopped = run_answer(round_, answer, history)
            if stopped is not None:
                break
        if stopped is not None:
            break
    stage = round_["stage"]
    state["revision"] += 1
    if not retry:
        # A retry repairs holes wherever they are; it does not move the student's stage.
        state["stage_index"] = STAGES.index(stage)
    room.result_json = state
    remaining = _missing(state)
    if stopped is not None:
        room.status = "budget_stopped"
        snapshot = load_interview_budget_snapshot(session, session_id=room_id,
                                                  run_budget_usd=settings.llm_budget_usd)
        left = max(snapshot.run_budget_usd - snapshot.run_spent_usd, Decimal("0"))
        room.error_json = {
            "code": stopped.code, "stage": stage, "room_id": room_id,
            "message": ("The budget stopped this room. Every answer you were charged for is still "
                        f"here and in order. ${left:.2f} of this run's ${snapshot.run_budget_usd:.2f} "
                        "budget remains, so the rest of the round was not started."),
            "details": stopped.details}
    elif remaining:
        room.status = "failed"
        room.error_json = {
            "code": "provider_unavailable", "stage": stage, "room_id": room_id,
            "message": "Some personas did not answer. Retry to run only the missing turns; "
                       "answers already collected are kept and are not charged again.",
            "missing": [{"round": index, "persona_id": pid} for index, pid in remaining]}
    else:
        room.status = "completed" if STAGES[state["stage_index"]] == "close" else "running"
        room.error_json = None
    room.heartbeat_at = service.utcnow()
    if room.status == "completed":
        room.completed_at = service.utcnow()
    session.commit()
    status = room_status(session, settings, study, room_id)
    status["charged_this_round"] = charged_any
    return status


def _check_recipients(seats, recipients):
    """None is the whole room. A selection is a subset of the seats; naming every seat is
    the whole room too."""
    if recipients is None:
        return None
    if (not isinstance(recipients, list) or not recipients
            or any(not isinstance(pid, str) for pid in recipients)):
        raise ValidationApiError("Choose at least one participant to ask, or ask the whole room.")
    if len(set(recipients)) != len(recipients):
        raise ValidationApiError("Each participant can only be selected once.")
    strangers = [pid for pid in recipients if pid not in seats]
    if strangers:
        raise ValidationApiError(f"{', '.join(strangers)} is not in this room.")
    return None if set(recipients) == set(seats) else [pid for pid in seats if pid in recipients]


def _check_reveal(state, stage, reveal):
    """A stimulus is released on purpose, once, in funnel order — and the price only after
    the room has answered an unaided price question."""
    if reveal is None:
        return
    if reveal not in STIMULI:
        raise ValidationApiError("Only the concept card or the price can be revealed.")
    rounds = state["rounds"]
    shown = _shown(rounds)
    if reveal in shown:
        raise ValidationApiError(f"The {reveal} has already been shown to this room.")
    if reveal == "concept" and STAGES.index(stage) < STAGES.index("concept"):
        raise ValidationApiError("Introduce the concept at the concept stage, not before it.")
    if reveal == "price":
        if "concept" not in shown:
            raise ValidationApiError("Introduce the concept before revealing its price.")
        if STAGES.index(stage) < STAGES.index("price_reactions"):
            raise ValidationApiError("Reveal the price at the price-reactions stage.")
        if not any(r["stage"] == "price_reactions" and any(a["status"] == "answered" for a in r["answers"])
                   for r in rounds):
            raise ValidationApiError(
                "Ask the unaided price question first (what would they expect it to cost?), "
                "then reveal the price.")


def _check_photo(photo, reveal, price_shown):
    """The student's product photo stays in their browser; only its filename and their
    description of it arrive here, and only with the concept introduction. Personas are text
    models, so the description is the only part of the photo they ever get."""
    if photo is None:
        return None
    if reveal != "concept":
        raise ValidationApiError("A product photo is shared only with the question that introduces the concept.")
    if not isinstance(photo, dict) or set(photo) - {"filename", "caption"}:
        raise ValidationApiError("Send only the photo's filename and description, never the image.")
    filename, caption = str(photo.get("filename") or "").strip(), str(photo.get("caption") or "").strip()
    if not filename or len(filename) > 200:
        raise ValidationApiError("The photo needs a filename of at most 200 characters.")
    if len(caption) > 500:
        raise ValidationApiError("Keep the photo description to 500 characters.")
    if not price_shown and _MONEY.search(caption):
        raise ValidationApiError(
            "Don't anchor price first — the photo description names a dollar figure. Remove it; "
            "use Reveal price later to share the price.")
    return {"filename": filename, "caption": caption}


def _stimulus_text(reveal, photo):
    if photo and photo["caption"]:
        return f"{STIMULI[reveal]}\nPhoto the moderator is showing (described in words): {photo['caption']}"
    return STIMULI[reveal]


def _photo_line(stimulus):
    photo = stimulus.get("photo")
    return f"Photo shown: {photo['filename']}, described as: {photo['caption'] or '(no description)'}" if photo else ""


def shared_view(rounds):
    """What participants had been shown, and from which round — the student's answer to
    'what has the room seen?'."""
    return [{"kind": r["stimulus"]["kind"], "round": r["index"], "turn_id": turn_id(r["index"]),
             "stage": r["stage"], "text": r["stimulus"]["text"]} for r in rounds if r.get("stimulus")]


@serialized_local
def extend_room(session, settings, study, room_id, payload):
    """More follow-up probes, bought on purpose. The added rounds' estimate is shown first,
    must be authorized, and has to fit the same run and class budget a room start does."""
    from src.services.interview_service import utcnow
    room = owned_room(session, study, room_id, lock=True)
    from src.services.demo_mode import refuse_demo
    refuse_demo(room)
    if type(payload.get("revision")) is not int:
        raise ValidationApiError("An integer room revision is required.")
    if room.status in {"cancelled", "completed"}:
        raise ConflictApiError(f"This room is {room.status}; it cannot be extended.")
    state = deepcopy(room.result_json)
    extra = payload.get("extra_rounds")
    if payload["revision"] != state["revision"]:
        last = (state.get("extensions") or [{}])[-1]
        if last.get("from_revision") == payload["revision"] == state["revision"] - 1 \
                and last.get("extra_rounds") == extra:
            return room_status(session, settings, study, room_id)  # a double-click extends once
        # A stale tab must not be told it succeeded when nothing was added (refuter SOL-2).
        raise ConflictApiError("The room changed since this page loaded (a question was asked or it was "
                               "already extended), so nothing was added or charged. Review the room and "
                               "confirm the extension again.")
    left = allowance(room.payload_json, state)["extensions_left"]
    if type(extra) is not int or not 1 <= extra <= left:
        raise ValidationApiError(f"Add between 1 and {left} probes." if left
                                 else "This room has already had its full extension.")
    if payload.get("authorize_charge") is not True:
        raise ValidationApiError("Confirm the extra probes' estimated charge first.")
    config = room.payload_json
    try:
        estimate = estimate_room_cost_usd(persona_count=len(config["persona_ids"]), rounds=extra,
                                          model_id=config.get("model"))
    except StopIteration:
        raise ConflictApiError("This room's model is no longer offered, so it cannot be extended.") from None
    lock_class_budget_for_transaction(session)
    snapshot = load_interview_budget_snapshot(session, session_id=room_id, run_budget_usd=settings.llm_budget_usd)
    enforce_budget_open(snapshot)
    # Same shape as the memo's preflight: what this room already spent plus what the
    # extension could spend must fit the run budget, and the class ceiling.
    enforce_run_preflight(estimated_cost_usd=estimate + snapshot.run_spent_usd,
                          class_spent_usd=snapshot.class_spent_usd - snapshot.run_spent_usd,
                          run_budget_usd=snapshot.run_budget_usd)
    state["extra_rounds"] = state.get("extra_rounds", 0) + extra
    state.setdefault("extensions", []).append(
        {"extra_rounds": extra, "estimated_cost_usd": str(estimate), "at": utcnow().isoformat(),
         "from_revision": state["revision"]})
    state["revision"] += 1
    room.result_json = state
    session.commit()
    return room_status(session, settings, study, room_id, room=room)


def _record_usage(session, study, room_id, persona_id, measured):
    """Accounting row. Empty text keeps focus-group turns out of the interview corpus."""
    from src.services.interview_service import utcnow
    session.add(InterviewTurn(study_id=study.id, persona_id=persona_id, session_id=room_id,
        role="assistant", text="", model=measured.model, tokens_in=measured.tokens_in,
        tokens_out=measured.tokens_out, cost_usd=measured.cost_usd, created_at=utcnow()))


# ---------------------------------------------------------------------------
# Memo: the PA3.5 hand-in fields, read off the student's own transcript
# ---------------------------------------------------------------------------

def _memo_prompt(room):
    return f"""You are helping a marketing-research student write the one-page memo for a focus group they just moderated.

Work ONLY from the transcript below. Every quote and every answer option must be copied \
VERBATIM from a participant's answer — character for character, no paraphrase, no invention, \
no cleanup. If you cannot find real supporting text, return fewer themes rather than inventing one.

Return ONLY a JSON object:
{{
  "themes": [
    {{"label": "...", "synthesis": "one sentence", "quote": "<verbatim>", "persona_id": "P0XX",
      "sentiment": "positive" | "neutral" | "negative"}}
  ],
  "surprise": {{"summary": "one sentence on the single most surprising thing", "quote": "<verbatim>", "persona_id": "P0XX"}},
  "answer_options": [
    {{"text": "<verbatim participant wording to use as a closed-ended survey option>", "persona_id": "P0XX"}}
  ]
}}

{MEMO_MIN_THEMES}–{MEMO_MAX_THEMES} themes, exactly one surprise, at least \
{MEMO_MIN_ANSWER_OPTIONS} answer options, each phrased in participant language."""


def _memo_transcript(state):
    lines = []
    for round_ in state["rounds"]:
        lines.append(f"## {STAGE_LABELS[round_['stage']]} — moderator: {round_['question']}")
        for answer in round_["answers"]:
            if answer["status"] == "answered":
                lines.append(f"{answer['persona_id']}: {answer['text']}")
    return "\n".join(lines)


def _locate(state, text, persona_id=None):
    """Where in the transcript this exact text appears, or None if it does not."""
    for round_ in state["rounds"]:
        for answer in round_["answers"]:
            if answer["status"] != "answered" or (persona_id and answer["persona_id"] != persona_id):
                continue
            if text and text in answer["text"]:
                return {"persona_id": answer["persona_id"], "round": round_["index"],
                        "stage": round_["stage"], "question": round_["question"]}
    return None


def _revision(state):
    """Which transcript a memo is about. The export compares against this too, so a memo
    written before the last round cannot be handed in unmarked (refuter FG-A).

    Turn IDs are stripped: room_status adds them on read, and the export hashes that view
    while the memo hashed the stored rounds — the two must agree."""
    rounds = [{**{k: v for k, v in r.items()
                  if k != "turn_id" and not (k == "stimulus" and v.get("derived"))},
               "answers": [{k: v for k, v in a.items() if k != "turn_id"} for a in r["answers"]]}
              for r in state.get("rounds", [])]
    return hashlib.sha256(json.dumps(rounds, sort_keys=True).encode()).hexdigest()


def memo_view(session, settings, study, room_id, room=None):
    room = room or owned_room(session, study, room_id)
    state = _normalized(room.result_json or {})
    answers = _answered(state)
    reached = {r["stage"] for r, _ in _answered({"rounds": _counted(state["rounds"])})}
    missing_stages = [s for s in MEMO_REQUIRED_STAGES if s not in reached]
    if missing_stages:
        eligible, message = False, (
            "This room never reached " + " or ".join(STAGE_LABELS[s] for s in missing_stages)
            + ". A memo written without those stages would be invented, not observed.")
    elif len(answers) < MEMO_MIN_ANSWERS:
        eligible, message = False, (
            f"This room has {len(answers)} answered turns. The memo needs at least "
            f"{MEMO_MIN_ANSWERS} before themes, a surprise, and answer options can be read "
            "off the transcript rather than padded.")
    else:
        eligible, message = True, "Write the memo from this transcript."
    revision = _revision(state)
    saved = state.get("memo")
    stale = bool(saved and saved["revision"] != revision)
    prompt = _memo_prompt(room) + _memo_transcript(state)
    model = next(m for m in list_interview_model_catalog()["models"] if m["id"] == MEMO_MODEL)
    estimate = (Decimal(len(prompt.encode()) + 100) * Decimal(str(model["prompt_price_per_million"]))
                + Decimal(2000) * Decimal(str(model["completion_price_per_million"]))) / _TOKENS_PER_MILLION
    return {"room_id": room.public_id, "revision": revision, "eligible": eligible, "message": message,
            "answered_turns": len(answers), "stages_reached": sorted(reached, key=STAGES.index),
            # "available" means a memo the student can hand in as-is. A memo written
            # before the last round describes a transcript that no longer exists, so it
            # is NOT available — that is what re-opens the rewrite control instead of
            # leaving the room with a stale memo and no way to refresh it (refuter FG-A).
            "available": bool(saved and saved.get("themes")) and not stale,
            "stale": stale,
            "estimated_cost_usd": str(estimate), "model": MEMO_MODEL, "saved": saved,
            "session_usage": usage(session, settings, room.public_id)}


@serialized_local
def focus_group_memo(session, settings, study, room_id, payload=None):
    """Read-only unless the student authorizes the charge; re-opening never pays twice."""
    from src.services import interview_service as service
    room = owned_room(session, study, room_id, lock=True)
    from src.services.demo_mode import refuse_demo
    if payload is not None:
        refuse_demo(room)
    view = memo_view(session, settings, study, room_id, room=room)
    if payload is None or not view["eligible"]:
        return view
    if payload.get("revision") != view["revision"]:
        raise ConflictApiError("The transcript changed. Review the new memo estimate before confirming.")
    saved = view["saved"]
    if saved and not view["stale"]:
        if saved.get("themes"):
            return view  # Already written. Re-opening it is free.
        if payload.get("retry_attempt") != saved.get("attempt"):
            return view
    if room.status == "cancelled":
        # cancel_room promises no further paid call against a cancelled room; the memo is
        # a paid call, so it has to honour that too. Reading an already-written memo stays
        # free — those paths returned above.
        raise ConflictApiError("This room was cancelled. Writing its memo would be a new charge.")
    if payload.get("authorize_charge") is not True:
        raise ValidationApiError("Confirm the additional memo charge first.")
    if settings.cache_mode == "replay_only":
        raise ConflictApiError("Cache-only mode: no saved memo exists for this transcript.")
    lock_class_budget_for_transaction(session)
    snapshot = load_interview_budget_snapshot(session, session_id=room_id, run_budget_usd=settings.llm_budget_usd)
    enforce_budget_open(snapshot)
    enforce_run_preflight(estimated_cost_usd=Decimal(view["estimated_cost_usd"]) + snapshot.run_spent_usd,
        class_spent_usd=snapshot.class_spent_usd - snapshot.run_spent_usd, run_budget_usd=snapshot.run_budget_usd)
    if not settings.openrouter_api_key:
        raise ConflictApiError("Memo writing is not configured.")
    state = deepcopy(room.result_json)
    attempt = (saved.get("attempt", 0) if saved else 0) + 1
    record = {"revision": view["revision"], "attempt": attempt, "outcome": "unknown", "themes": None}
    try:
        try:
            result = service._call_openrouter_messages(api_key=settings.openrouter_api_key, model=MEMO_MODEL,
                messages=[{"role": "system", "content": _memo_prompt(room)},
                          {"role": "user", "content": f"FOCUS GROUP TRANSCRIPT:\n{_memo_transcript(state)}"}],
                timeout=PROVIDER_TIMEOUT_SECONDS, max_attempts=1)
        except TransientProviderError as exc:
            # Billed but unusable still costs money; record it before failing.
            if exc.measured_usage is not None:
                _record_usage(session, study, room_id, "__memo__", exc.measured_usage)
                record.update(outcome="charged", cost_usd=str(exc.measured_usage.cost_usd))
            raise
        _record_usage(session, study, room_id, "__memo__", result)
        record.update(outcome="charged", cost_usd=str(result.cost_usd))
        try:
            enforce_measured_cost(snapshot, cost_usd=result.cost_usd)
        except QuotaExceededApiError as exc:
            record["budget_stop"] = exc.message
        record.update(_validate_memo(json.loads(result.text), state))
    except Exception as exc:
        # Say WHY in the student's terms: a validation reason is ours and safe to show; a
        # provider error is not, so it collapses to "the provider did not answer".
        record["reason"] = ("the response was not in the memo format" if isinstance(exc, json.JSONDecodeError)
                            else f"it could not be validated against the transcript ({exc})"
                            if isinstance(exc, ValueError)
                            else "the AI provider did not return a usable answer")
        charge = (f"This attempt was charged ${Decimal(record['cost_usd']):.4f}, and that charge is "
                  "recorded against your budget." if record["outcome"] == "charged"
                  else "The provider's billing outcome for this attempt is unknown.")
        record["message"] = (
            f"The AI draft could not be used: {record['reason']}. Your transcript and your own memo "
            f"are preserved. {charge} You can finish your memo by hand and export it now without "
            f"another attempt; retrying the AI draft is a new charge of about "
            f"${Decimal(view['estimated_cost_usd']):.4f}.")
    logger.log(logging.INFO if record["themes"] else logging.WARNING,
               "focus_group_memo study=%s room=%s revision=%s attempt=%s outcome=%s valid=%s",
               study.public_id, room_id, view["revision"], attempt, record["outcome"], bool(record["themes"]))
    state["memo"] = record
    room.result_json = state
    session.commit()
    return memo_view(session, settings, study, room_id, room=room)


def _validate_memo(parsed, state):
    """Accept only memo fields that can be pointed at in the transcript."""
    themes = parsed.get("themes")
    surprise = parsed.get("surprise")
    options = parsed.get("answer_options")
    if not isinstance(themes, list) or not MEMO_MIN_THEMES <= len(themes) <= MEMO_MAX_THEMES:
        raise ValueError(f"Expected {MEMO_MIN_THEMES}–{MEMO_MAX_THEMES} themes")
    located_themes = []
    for theme in themes:
        if (not isinstance(theme, dict)
                or any(not isinstance(theme.get(k), str) or not theme[k].strip()
                       for k in ("label", "synthesis", "quote", "persona_id"))
                or theme.get("sentiment") not in ("positive", "neutral", "negative")):
            raise ValueError("Invalid theme")
        found = _locate(state, theme["quote"], theme["persona_id"])
        if not found:
            raise ValueError("Theme quote is not verbatim from this transcript")
        located_themes.append({**theme, "located_at": found})
    if (not isinstance(surprise, dict)
            or any(not isinstance(surprise.get(k), str) or not surprise[k].strip()
                   for k in ("summary", "quote", "persona_id"))):
        raise ValueError("Expected exactly one surprise")
    surprise_at = _locate(state, surprise["quote"], surprise["persona_id"])
    if not surprise_at:
        raise ValueError("Surprise quote is not verbatim from this transcript")
    if not isinstance(options, list) or len(options) < MEMO_MIN_ANSWER_OPTIONS:
        raise ValueError(f"Expected at least {MEMO_MIN_ANSWER_OPTIONS} answer options")
    located_options = []
    for option in options:
        # persona_id is required here for the same reason it is on themes and the surprise:
        # without it _locate falls back to the first containment hit, and option wording
        # distilled from a group routinely appears in more than one persona's answer — so a
        # student would hand in participant language credited to a participant who may not
        # have said it. Refusing is better than guessing at attribution (refuter FG-6).
        if (not isinstance(option, dict)
                or any(not isinstance(option.get(k), str) or not option[k].strip()
                       for k in ("text", "persona_id"))):
            raise ValueError("Invalid answer option")
        found = _locate(state, option["text"], option["persona_id"])
        if not found:
            raise ValueError("Answer option is not verbatim participant language")
        located_options.append({**option, "located_at": found})
    return {"themes": located_themes, "surprise": {**surprise, "located_at": surprise_at},
            "answer_options": located_options}


# ---------------------------------------------------------------------------
# Manual memo: the student's own analysis, no model involved
# ---------------------------------------------------------------------------

MANUAL_MAX_THEMES, MANUAL_MAX_QUOTES, MANUAL_MAX_OPTIONS = MEMO_MAX_THEMES, 5, 12
_SHORT, _LONG = 200, 2000


def _manual_text(value, field, limit):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationApiError(f"{field} must be text.")
    value = value.strip()
    if len(value) > limit:
        raise ValidationApiError(f"{field} is longer than {limit} characters.")
    return value


def _manual_list(value, field, limit):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationApiError(f"{field} must be a list.")
    if len(value) > limit:
        raise ValidationApiError(f"{field} holds at most {limit} entries.")
    if any(not isinstance(entry, dict) for entry in value):
        raise ValidationApiError(f"Each entry in {field} must be an object.")
    return value


def _manual_quote(value, field):
    if value is None:
        return {"turn_id": "", "text": ""}
    if not isinstance(value, dict):
        raise ValidationApiError(f"{field} must name a turn and the words quoted from it.")
    return {"turn_id": _manual_text(value.get("turn_id"), f"{field} turn", 40),
            "text": _manual_text(value.get("text"), f"{field} text", _LONG)}


def _clean_manual_memo(raw):
    """The trust boundary: shape and size only. Whether it is COMPLETE is a separate
    question (manual_memo_check), so a half-written memo still saves."""
    if not isinstance(raw, dict):
        raise ValidationApiError("Send the memo as an object.")
    themes = [{"label": _manual_text(t.get("label"), "Theme label", _SHORT),
               "synthesis": _manual_text(t.get("synthesis"), "Theme summary", _LONG),
               "quotes": [_manual_quote(q, "Theme quote")
                          for q in _manual_list(t.get("quotes"), "Theme quotes", MANUAL_MAX_QUOTES)]}
              for t in _manual_list(raw.get("themes"), "Themes", MANUAL_MAX_THEMES)]
    surprise = raw.get("surprise") or {}
    if not isinstance(surprise, dict):
        raise ValidationApiError("The surprise must be an object.")
    options = [{"text": _manual_text(o.get("text"), "Answer option", _SHORT),
                "topic": _manual_text(o.get("topic"), "Answer option topic", _SHORT),
                "turn_id": _manual_text(o.get("turn_id"), "Answer option turn", 40)}
               for o in _manual_list(raw.get("answer_options"), "Answer options", MANUAL_MAX_OPTIONS)]
    return {"themes": themes,
            "surprise": {"summary": _manual_text(surprise.get("summary"), "Surprise", _LONG),
                         "quote": _manual_quote(surprise.get("quote"), "Surprise quote")},
            "answer_options": options,
            "moderation_improvement": _manual_text(raw.get("moderation_improvement"),
                                                   "Moderation improvement", _LONG)}


def _answered_turns(state):
    return {turn_id(r["index"], a["persona_id"]): {
                "turn_id": turn_id(r["index"], a["persona_id"]), "persona_id": a["persona_id"],
                "round": r["index"], "stage": r["stage"], "question": r["question"], "text": a["text"]}
            for r in state.get("rounds", []) for a in r["answers"] if a["status"] == "answered"}


def _quote_problem(quote, turns):
    """None if the quote is words copied from a real answered turn; otherwise why not."""
    if not quote.get("turn_id"):
        return "has no quote picked from the transcript"
    turn = turns.get(quote["turn_id"])
    if turn is None:
        return f"cites {quote['turn_id']}, which is not an answered turn in this transcript"
    if not quote.get("text") or quote["text"] not in turn["text"]:
        return f"quote is not the words {turn['persona_id']} said in {quote['turn_id']}"
    return None


def manual_memo_check(state):
    """Checked against the transcript as it is NOW, so a quote can never claim a link
    it does not have."""
    memo = state.get("manual_memo")
    if not memo:
        return {"saved": False, "complete": False, "problems": ["Not started."]}
    turns = _answered_turns(state)
    problems = []
    themes = [t for t in memo["themes"] if t["label"] or t["synthesis"] or t["quotes"]]
    if len(themes) < MEMO_MIN_THEMES:
        problems.append(f"Write at least {MEMO_MIN_THEMES} themes ({len(themes)} so far).")
    for n, theme in enumerate(themes, 1):
        if not theme["label"]:
            problems.append(f"Theme {n} needs a label.")
        if not theme["quotes"]:
            problems.append(f"Theme {n} needs at least one quote picked from the transcript.")
        for quote in theme["quotes"]:
            if (why := _quote_problem(quote, turns)):
                problems.append(f"Theme {n}: {why}.")
    if not memo["surprise"]["summary"]:
        problems.append("Describe one surprise.")
    if (why := _quote_problem(memo["surprise"]["quote"], turns)):
        problems.append(f"Surprise {why}.")
    options = [o for o in memo["answer_options"] if o["text"] or o["topic"]]
    if len(options) < MEMO_MIN_ANSWER_OPTIONS:
        problems.append(f"Write at least {MEMO_MIN_ANSWER_OPTIONS} PA4 answer options ({len(options)} so far).")
    for n, option in enumerate(options, 1):
        if not option["text"] or not option["topic"]:
            problems.append(f"Answer option {n} needs both its wording and the question topic it answers.")
        if option["turn_id"] and option["turn_id"] not in turns:
            problems.append(f"Answer option {n} cites {option['turn_id']}, which is not an answered turn.")
    if not memo["moderation_improvement"]:
        problems.append("Name one thing you would change about how you moderated.")
    return {"saved": True, "complete": not problems, "problems": problems}


def _memo_is_blank(memo):
    quotes = [q for t in memo["themes"] for q in t["quotes"]] + [memo["surprise"]["quote"]]
    return not any([*(t["label"] or t["synthesis"] for t in memo["themes"]), memo["surprise"]["summary"],
                    *(q["turn_id"] or q["text"] for q in quotes),
                    *(o["text"] or o["topic"] or o["turn_id"] for o in memo["answer_options"]),
                    memo["moderation_improvement"]])


@serialized_local
def save_manual_memo(session, settings, study, room_id, payload):
    """Free, and allowed in every room state: the student's own writing never waits on
    a model, a budget, or a room that was ended."""
    from src.services.interview_service import utcnow
    room = owned_room(session, study, room_id, lock=True)
    memo = _clean_manual_memo((payload or {}).get("memo"))
    base = (payload or {}).get("base_version")
    if type(base) is not int:
        raise ValidationApiError("Reload the page before saving: the memo version it was opened at is missing.")
    state = deepcopy(room.result_json)
    saved = state.get("manual_memo")
    version = (saved or {}).get("version", 0)
    if base != version:
        # Another tab (or an export from one) saved since this page loaded. Overwriting it
        # would silently lose the newer memo (refuter EXPORT-IMPLICIT-SAVE-OVERWRITES).
        raise ConflictApiError("Your memo was saved from another tab or window after this page loaded, so "
                               "this save was refused to keep that newer version. Copy anything you need "
                               "from this page, then re-open the room to see the saved memo.")
    if saved is None and _memo_is_blank(memo):
        # Nothing written: an untouched form is not a draft, and the export keeps saying
        # "Not written yet" instead of listing blank padding.
        return room_status(session, settings, study, room_id, room=room)
    state["manual_memo"] = {**memo, "saved_at": utcnow().isoformat(), "version": version + 1}
    room.result_json = state
    session.commit()
    return room_status(session, settings, study, room_id, room=room)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _manual_memo_rows(status):
    """The student's memo as (field, speaker, label, text, link_status, turn_id, location) rows,
    each quote resolved against the transcript so the export can only call linked what is."""
    memo = status.get("manual_memo")
    if not memo:
        return []
    turns = _answered_turns(status)
    rows = []

    def quote_row(field, label, quote):
        why = _quote_problem(quote, turns)
        turn = turns.get(quote.get("turn_id"))
        rows.append((field, turn["persona_id"] if turn and not why else "", label, quote.get("text", ""),
                     "not_linked" if why else "linked", quote.get("turn_id", ""), why or turn))

    # The form pads to three themes and three options; blank padding is not memo content.
    for theme in [t for t in memo["themes"] if t["label"] or t["synthesis"] or t["quotes"]]:
        rows.append(("theme", "", theme["label"], theme["synthesis"], "", "", None))
        for quote in theme["quotes"]:
            quote_row("theme_quote", theme["label"], quote)
    rows.append(("surprise", "", "", memo["surprise"]["summary"], "", "", None))
    quote_row("surprise_quote", "", memo["surprise"]["quote"])
    for option in [o for o in memo["answer_options"] if o["text"] or o["topic"]]:
        turn = turns.get(option["turn_id"])
        rows.append(("answer_option", turn["persona_id"] if turn else "", option["topic"], option["text"],
                     "linked" if turn else ("not_linked" if option["turn_id"] else ""), option["turn_id"], turn))
    rows.append(("moderation_improvement", "", "", memo["moderation_improvement"], "", "", None))
    return rows


def _origin_line(status, persona_id):
    custom = status.get("custom_personas", {}).get(persona_id)
    if not custom:
        return "roster persona grounded in one ACS household record (name invented)"
    card = custom["card"]
    line = f"Student-created fictional persona, version {custom['version']}"
    if custom.get("based_on"):
        line += f", started from a copy of {custom['based_on']}"
    return (line + ". Not a real PA3.5 participant. How it relates to the research question: "
            + (card.get("research_link") or "not given"))


def build_room_export(status, export_format):
    """Markdown or CSV of the transcript and memos, attributed turn by turn."""
    from src.services.interview_export import InterviewTranscriptExport, _as_csv_text
    import csv
    import io
    room_id = status["room_id"]
    incomplete = [f"{r['index']}:{a['persona_id']}" for r in status["rounds"]
                  for a in r["answers"] if a["status"] == "missing"]
    unfinished = status["status"] != "completed" or bool(incomplete)
    memo = (status.get("memo") or {}) if isinstance(status.get("memo"), dict) else {}
    memo_stale = bool(memo.get("themes") and memo.get("revision") != _revision(status))
    check = manual_memo_check(status)
    manual_rows = _manual_memo_rows(status)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", room_id).strip(".-")[:64] or "room"

    if export_format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        # ponytail: the label is the first row so no one opens the file without seeing it;
        # a parser that wants the header first skips one line.
        writer.writerow([REHEARSAL_LABEL])
        if status.get("demo"):
            writer.writerow([status["demo_label"], "Playback cost: $0"])
            if status.get("provisional"):
                writer.writerow(["Provisional hand-written example"])
        writer.writerow(["round", "stage", "speaker", "role", "text", "status", "complete", "turn_id"])
        for round_ in status["rounds"]:
            if round_.get("stimulus"):
                writer.writerow([round_["index"] + 1, round_["stage"], "Stimulus", "shown_to_participants",
                                 _as_csv_text(round_["stimulus"]["text"]), round_["stimulus"]["kind"],
                                 str(not unfinished), f"R{round_['index'] + 1}-STIMULUS"])
                if _photo_line(round_["stimulus"]):
                    writer.writerow([round_["index"] + 1, round_["stage"], "Stimulus", "photo_record",
                                     _as_csv_text(_photo_line(round_["stimulus"])), "photo",
                                     str(not unfinished), f"R{round_['index'] + 1}-PHOTO"])
            writer.writerow([round_["index"] + 1, round_["stage"], "Moderator", "moderator",
                             _as_csv_text(round_["question"]), "asked", str(not unfinished),
                             turn_id(round_["index"])])
            for answer in round_["answers"]:
                writer.writerow([round_["index"] + 1, round_["stage"], _as_csv_text(answer["persona_id"]),
                                 "participant", _as_csv_text(answer["text"]), answer["status"],
                                 str(not unfinished), turn_id(round_["index"], answer["persona_id"])])
        writer.writerow([])
        writer.writerow(["participant", "persona_id", "origin", "version", "based_on", "real_pa35_participant",
                         "complete", "turn_id"])
        for pid in status["persona_ids"]:
            custom = status.get("custom_personas", {}).get(pid)
            writer.writerow(["participant", pid, "student_created_fictional" if custom else "source_grounded_roster",
                             custom["version"] if custom else "", (custom or {}).get("based_on") or "", "False",
                             str(not unfinished), ""])
        if manual_rows:
            writer.writerow([])
            writer.writerow(["student_memo", "field", "speaker", "label_or_topic", "text", "link",
                             "complete", "turn_id"])
            for field, speaker, label, text, link, tid, _ in manual_rows:
                writer.writerow(["student_memo", field, _as_csv_text(speaker), _as_csv_text(label),
                                 _as_csv_text(text), link, str(check["complete"]), _as_csv_text(tid)])
        # The docstring and the UI button both promise the memo; the CSV used to stop at
        # the transcript and say nothing about it (refuter FG-B).
        if memo.get("themes"):
            fresh = str(not unfinished and not memo_stale)
            memo_status = "out_of_date" if memo_stale else "current"
            writer.writerow([])
            writer.writerow(["memo", "field", "speaker", "role", "text", "status", "complete", "turn_id"])
            for theme in memo["themes"]:
                at = theme["located_at"]
                writer.writerow(["memo", "theme", _as_csv_text(at["persona_id"]),
                                 theme["sentiment"],
                                 _as_csv_text(f"{theme['label']}: {theme['synthesis']} - \"{theme['quote']}\""),
                                 memo_status, fresh, turn_id(at["round"], at["persona_id"])])
            surprise = memo["surprise"]
            at = surprise["located_at"]
            writer.writerow(["memo", "surprise", _as_csv_text(at["persona_id"]),
                             "surprise",
                             _as_csv_text(f"{surprise['summary']} - \"{surprise['quote']}\""),
                             memo_status, fresh, turn_id(at["round"], at["persona_id"])])
            for option in memo["answer_options"]:
                at = option["located_at"]
                writer.writerow(["memo", "answer_option", _as_csv_text(at["persona_id"]),
                                 "answer_option", _as_csv_text(option["text"]), memo_status, fresh,
                                 turn_id(at["round"], at["persona_id"])])
        return InterviewTranscriptExport(content="\ufeff" + output.getvalue(),
            filename=f"focus-group-{stem}.csv", media_type="text/csv")

    lines = ["# Focus group transcript", "",
             f"> **{REHEARSAL_LABEL}.** Every participant below is a simulated persona, not a real "
             "person. Nothing here is PA3.5 fieldwork or evidence about real customers.", ""]
    if status.get("demo"):
        lines += [status["demo_label"], "Playback cost: $0", "Provisional hand-written example" if status.get("provisional") else "", ""]
    if unfinished:
        lines += [f"> **INCOMPLETE — do not submit as final.** Room status: `{status['status']}`."
                  + (f" Missing answers (round:persona): {', '.join(incomplete)}." if incomplete else ""), ""]
    lines += [f"- Room: `{room_id}`", f"- Model: `{status.get('model') or 'unknown'}`",
              f"- Participants: {', '.join(status['persona_ids'])}",
              *(f"  - {pid}: {_origin_line(status, pid)}" for pid in status["persona_ids"]),
              "- Real PA3.5 participants in this room: 0 — every participant is simulated.",
              f"- Stages reached: {', '.join(STAGE_LABELS[s] for s in status['stages_reached']) or 'none'}"]
    shared = {item["kind"]: item for item in shared_view(status["rounds"])}
    for kind, label in (("concept", "Concept introduced"), ("price", "Price revealed")):
        item = shared.get(kind)
        lines.append(f"- {label}: " + (f"before round {item['round'] + 1} (`{item['turn_id']}`)" if item
                                       else "never — participants were not shown it"))
    lines.append("")
    for round_ in status["rounds"]:
        lines += [f"## {round_['index'] + 1}. {STAGE_LABELS[round_['stage']]}"
                  + (" — asked after participants had been shown the concept" if round_.get("post_exposure") else ""),
                  ""]
        if round_.get("stimulus"):
            how = (" — by this stage, in the prompt, before Introduce/Reveal existed"
                   if round_["stimulus"].get("derived") else "")
            lines += [f"**Shown to participants with this question ({round_['stimulus']['kind']}{how}):**", "",
                      *(f"> {line}" for line in round_["stimulus"]["text"].splitlines()), ""]
            if _photo_line(round_["stimulus"]):
                lines += [f"**{_photo_line(round_['stimulus'])}**", ""]
        to = f" _(to {', '.join(round_['recipients'])} only)_" if round_.get("recipients") else ""
        lines += [f"**Moderator:**{to} {round_['question']} `[{turn_id(round_['index'])}]`", ""]
        for answer in round_["answers"]:
            tid = turn_id(round_["index"], answer["persona_id"])
            if answer["status"] == "answered":
                lines += [f"**{answer['persona_id']}:** {answer['text']} `[{tid}]`", ""]
            elif answer["status"] == "silent":
                lines += [f"_{answer['persona_id']} was not asked this question (intentionally silent)._", ""]
            else:
                lines += [f"**{answer['persona_id']}:** _no answer — {answer['status']}_ `[{tid}]`", ""]
    lines += ["## Student memo (written by the student)", ""]
    if not manual_rows:
        lines += ["_Not written yet._", ""]
    else:
        if not check["complete"]:
            lines += ["> **DRAFT — not complete.** Still missing: " + " ".join(check["problems"]), ""]

        def cite(tid, text, link, where):
            if link != "linked":
                return f"  - \"{text}\" — NOT LINKED: {where}"
            return (f"  - \"{text}\" — {where['persona_id']} `[{tid}]`, "
                    f"{STAGE_LABELS[where['stage']]} round {where['round'] + 1}")

        section = None
        for field, _, label, text, link, tid, where in manual_rows:
            heading = {"theme": "### Themes", "surprise": "### One surprise",
                       "answer_option": "### PA4 answer options (tagged by question topic)",
                       "moderation_improvement": "### What I would change as moderator"}.get(field)
            if heading and heading != section:
                lines += ["", heading, ""]
                section = heading
            if field == "theme":
                lines.append(f"- **{label or '(no label)'}** — {text}")
            elif field in ("theme_quote", "surprise_quote"):
                lines.append(cite(tid, text, link, where))
            elif field == "answer_option":
                source = f" — from {where['persona_id']} `[{tid}]`" if link == "linked" else ""
                lines.append(f"- [{label or 'no topic'}] \"{text}\"{source}")
            else:
                lines.append(text)
        lines.append("")
    if memo.get("themes"):
        lines += ["## AI draft memo (optional feedback, not the student's analysis)", ""]
        if memo_stale:
            lines += ["> **OUT OF DATE — do not submit as final.** This memo was written before "
                      "the last round below and does not describe it. Rewrite the memo.", ""]
        lines += ["### Themes", ""]
        for theme in memo["themes"]:
            at = theme["located_at"]
            lines += [f"- **{theme['label']}** ({theme['sentiment']}) — {theme['synthesis']}",
                      f"  - \"{theme['quote']}\" — {theme['persona_id']} `[{turn_id(at['round'], at['persona_id'])}]`, "
                      f"{STAGE_LABELS[at['stage']]} round {at['round'] + 1}"]
        surprise = memo["surprise"]
        lines += ["", "### One surprise", "", f"{surprise['summary']}",
                  f"- \"{surprise['quote']}\" — {surprise['persona_id']}", "",
                  "### Closed-ended answer options (participant language)", ""]
        # Attribute from located_at, the transcript position _validate_memo verified the
        # option against. The validator requires persona_id on options (FG-6), so the two
        # agree by construction; located_at is the one the transcript itself vouches for.
        lines += [f"- \"{option['text']}\" — {option['located_at']['persona_id']}"
                  for option in memo["answer_options"]]
        lines.append("")
    return InterviewTranscriptExport(content="\n".join(lines),
        filename=f"focus-group-{stem}.md", media_type="text/markdown")


def export_room(session, settings, study, room_id, payload):
    export_format = str((payload or {}).get("format") or "markdown")
    if export_format not in ("markdown", "csv"):
        raise ValidationApiError("Export format must be markdown or csv.")
    status = room_status(session, settings, study, room_id)
    export = build_room_export(status, export_format)
    return {"content": export.content, "filename": export.filename,
            "media_type": export.media_type, "complete": status["complete"]}
