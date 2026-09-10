"""Phase 2 — run a persona CSV through the survey headlessly, one OpenRouter call per persona.

Reuses the app's own live-run function (`_generate_live_response_records_with_debug` in
apps/api/src/adapters/legacy_backend/domain.py) so the runner inherits, unchanged, the app's
prompt construction, order-preserving concurrency, fail-fast on non-retryable provider errors,
answer coercion, and per-answer fallback flagging. The engine is not modified; the three
collaborators the adapter takes as parameters are replaced by thin shims:

* a prompt-builder shim that raises max_tokens (39 answers do not fit in the engine's 1200) and
  tags each payload with its persona id;
* an OpenRouter client shim that adds a seed, optional provider routing, retries on transient
  failures only, and keeps token usage, provider, and generation id for the manifest;
* a run-manager shim that maps a likert answered with its label ("Very interested") onto the
  scale instead of discarding it, and counts every time it does so.

Persona records reach the prompt through a PersonaProfile subclass whose model_dump() carries the
exact Census fields and the story, because the engine embeds persona.model_dump() verbatim.

Nothing here reads the real AYTM data. Every path argument is checked against the real-data
folder names before any network call.

Usage (from the repository root):

    apps/api/.venv/bin/python research/neo_persona_set/phase2/run_survey.py --dry-run
    apps/api/.venv/bin/python research/neo_persona_set/phase2/run_survey.py \
        --models deepseek/deepseek-v4-pro-0813 --repeats 1 --limit 5
    apps/api/.venv/bin/python research/neo_persona_set/phase2/run_survey.py \
        --models deepseek/deepseek-v4-pro-0813 qwen/qwen3.7-plus --repeats 2 --concurrency 12
    apps/api/.venv/bin/python research/neo_persona_set/phase2/run_survey.py --summary <run_id> ...
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.adapters.legacy_backend import domain  # noqa: E402
from src.adapters.legacy_backend.runtime import ensure_legacy_root, load_module  # noqa: E402
from src.services.exceptions import ApiError  # noqa: E402

# ---------------------------------------------------------------------------
# Environment: read apps/api/.env directly. The app's settings object is not used because it
# validates database and deployment settings this script never needs.
# ---------------------------------------------------------------------------

_ENV_FILE_VALUES = {k: v for k, v in dotenv_values(API_ROOT / ".env").items() if v is not None}


def env_value(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None or not value.strip():
        value = _ENV_FILE_VALUES.get(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


def _resolve_legacy_root() -> Path:
    raw = env_value("LEGACY_APP_ROOT", "./legacy_runtime")
    path = Path(raw)
    if not path.is_absolute():
        path = (API_ROOT / path).resolve()
    return path


LEGACY_ROOT = _resolve_legacy_root()
ensure_legacy_root(LEGACY_ROOT)
schemas = load_module("backend.schemas", LEGACY_ROOT)
run_manager = load_module("backend.simulation.run_manager", LEGACY_ROOT)
prompt_builder = load_module("backend.simulation.prompt_builder", LEGACY_ROOT)
llm_client = load_module("backend.simulation.llm_client", LEGACY_ROOT)
presets = load_module("backend.presets", LEGACY_ROOT)

DEFAULT_PERSONAS = (
    REPO_ROOT.parent / "SyntheticResponderLab-Assets" / "600_persona" / "phase1_interview_survey600owners.csv"
)
DEFAULT_SURVEY = LEGACY_ROOT / "Provided Info" / "Neo Smart Living — Survey_HighMedPriority.md"
DEFAULT_OUT_DIR = REPO_ROOT.parent / "SyntheticResponderLab-Assets" / "600_persona" / "survey_runs"
DEFAULT_MODELS = ["deepseek/deepseek-v4-pro-0813", "qwen/qwen3.7-plus"]
DEFAULT_SEED_BASE = 20260909

# USD per million tokens (input, output), OpenRouter list prices on 2026-09-09.
PRICE_TABLE: Dict[str, Tuple[float, float]] = {
    "deepseek/deepseek-v4-pro-0813": (0.66, 1.98),
    "qwen/qwen3.7-plus": (0.32, 1.28),
    "qwen/qwen3.7-flash": (0.03, 0.13),
    "openai/gpt-4.1-mini": (0.40, 1.60),
}

# Substrings that identify the withheld real-respondent material. Any input or output path
# containing one of these is refused before a single request is sent.
REAL_DATA_MARKERS = ("aytm", "survey-760085", "raw 600-participant", "tony visit")

BUCKET_COLUMNS = ["persona_id", "age_bucket", "income_bucket", "ownership", "work_mode", "home_type"]
CLASSIFIER_COLUMNS = [
    "fit_tier",
    "awareness_stage",
    "segment_label",
    "likely_use_case",
    "likely_barrier",
    "affordability_pressure",
]
CENSUS_COLUMNS = [
    "exact_age",
    "exact_household_income",
    "sex",
    "county",
    "marital_status",
    "education",
    "occupation",
    "employment_status",
    "hours_worked_per_week",
    "commute_mode",
    "commute_minutes",
    "household_size",
    "children_in_household",
    "household_type",
    "tenure_detail",
    "bedrooms",
    "rooms",
    "year_built",
    "moved_in",
    "vehicles",
    "housing_cost_pct_of_income",
]
CENSUS_INT_COLUMNS = {
    "exact_age",
    "exact_household_income",
    "hours_worked_per_week",
    "commute_minutes",
    "household_size",
    "children_in_household",
    "bedrooms",
    "rooms",
    "housing_cost_pct_of_income",
}
STORY_PREFIX = "story_"
STORY_LIST_FIELDS = {"priorities"}

PROMPT_VARIANTS = ("full", "census", "buckets")
RESPONDENT_ID_PATTERN = re.compile(r"RESP_(\d+)")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Guard against the withheld real data
# ---------------------------------------------------------------------------


class RealDataPathError(SystemExit):
    def __init__(self, message: str) -> None:
        super().__init__(3)
        self.message = message


def assert_not_real_data(path: Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    lowered = str(resolved).lower()
    for marker in REAL_DATA_MARKERS:
        if marker in lowered:
            print(
                f"REFUSED: {label} path {resolved} names the withheld real-respondent material ({marker!r}).",
                file=sys.stderr,
            )
            raise RealDataPathError(f"{label} path names real data: {resolved}")
    return resolved


def assert_persona_header_is_synthetic(header: List[str], path: Path) -> None:
    survey_like = [column for column in header if re.match(r"^(S\d|Q\d|PQ\d)", column.strip())]
    if survey_like:
        print(
            f"REFUSED: {path} has survey-answer columns {survey_like[:5]}; this is not a persona file.",
            file=sys.stderr,
        )
        raise RealDataPathError(f"persona file looks like survey data: {path}")


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------


class RichPersonaProfile(schemas.PersonaProfile):  # type: ignore[misc,name-defined]
    """PersonaProfile plus the exact Census record and the written story.

    The engine embeds persona.model_dump() in the prompt, so these extra fields reach the model
    without any change to the prompt builder. None-valued fields are excluded so the six blank
    classifier columns do not appear as nulls.
    """

    name: Optional[str] = None
    census_record: Optional[Dict[str, Any]] = None
    story: Optional[Dict[str, Any]] = None

    def model_dump(self, **kwargs: Any) -> Dict[str, Any]:  # type: ignore[override]
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_int(value: Optional[str]) -> Optional[int]:
    text = _clean(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def build_persona(row: Dict[str, str], prompt_variant: str) -> RichPersonaProfile:
    if prompt_variant not in PROMPT_VARIANTS:
        raise ValueError(f"prompt_variant must be one of {PROMPT_VARIANTS}, got {prompt_variant!r}")

    fields: Dict[str, Any] = {column: _clean(row.get(column)) for column in BUCKET_COLUMNS}
    fields["lifestyle_tags"] = [tag.strip() for tag in (row.get("lifestyle_tags") or "").split(";") if tag.strip()]
    for column in CLASSIFIER_COLUMNS:
        fields[column] = _clean(row.get(column))

    if prompt_variant in ("full", "census"):
        fields["name"] = _clean(row.get("name"))
        census: Dict[str, Any] = OrderedDict()
        for column in CENSUS_COLUMNS:
            value: Any = _to_int(row.get(column)) if column in CENSUS_INT_COLUMNS else _clean(row.get(column))
            if value is not None:
                census[column] = value
        fields["census_record"] = census or None

    if prompt_variant == "full":
        story: Dict[str, Any] = OrderedDict()
        for column, raw in row.items():
            if not column.startswith(STORY_PREFIX):
                continue
            key = column[len(STORY_PREFIX) :]
            text = _clean(raw)
            if text is None:
                continue
            if key in STORY_LIST_FIELDS:
                story[key] = [item.strip() for item in text.split(";") if item.strip()]
            else:
                story[key] = text
        fields["story"] = story or None

    return RichPersonaProfile(**fields)


def load_personas(path: Path, *, limit: Optional[int], prompt_variant: str) -> List[RichPersonaProfile]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        assert_persona_header_is_synthetic(header, path)
        if "persona_id" not in header:
            raise ValueError(f"{path} has no persona_id column")
        rows = list(reader)
    if limit is not None:
        rows = rows[: int(limit)]
    personas = [build_persona(row, prompt_variant) for row in rows]
    ids = [persona.persona_id for persona in personas]
    duplicates = [pid for pid, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise ValueError(f"duplicate persona ids in {path}: {duplicates[:5]}")
    if not personas:
        raise ValueError(f"no personas loaded from {path}")
    return personas


def persona_census_lookup(path: Path) -> Dict[str, Dict[str, Any]]:
    """persona_id -> {exact_age, exact_household_income} for the consistency checks."""
    lookup: Dict[str, Dict[str, Any]] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            lookup[row["persona_id"]] = {
                "exact_age": _to_int(row.get("exact_age")),
                "exact_household_income": _to_int(row.get("exact_household_income")),
            }
    return lookup


# ---------------------------------------------------------------------------
# Survey, context, config
# ---------------------------------------------------------------------------


def load_survey(path: Path) -> Any:
    payload = domain.parse_normalize_validate_survey(path.name, path.read_bytes(), LEGACY_ROOT)
    return schemas.SurveySchema(**payload)


def load_contexts() -> Tuple[Any, Any]:
    return presets.get_neo_business_product_defaults(), presets.get_neo_market_defaults()


def build_config(*, run_id: str, survey: Any, personas: List[Any], model: str, notes: str) -> Any:
    return schemas.SimulationRunConfig(
        run_id=run_id,
        survey_title=survey.survey_title,
        survey_question_count=len(survey.questions),
        sample_size=len(personas),
        selected_models=[model],
        experiment_mode="split",
        reruns_per_persona=1,
        status="running",
        notes=notes,
    )


def model_slug(model: str) -> str:
    return model.split("/")[-1].replace(":", "-")


def make_run_id(model: str, repeat: int, *, limit: Optional[int], tag: Optional[str], now: Optional[datetime] = None) -> str:
    stamp = (now or utcnow()).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}_{model_slug(model)}_r{repeat}"
    if limit is not None:
        run_id += f"_n{limit}"
    if tag:
        run_id += f"_{re.sub(r'[^A-Za-z0-9_-]+', '-', tag)}"
    return run_id


# ---------------------------------------------------------------------------
# Shims handed to the adapter
# ---------------------------------------------------------------------------


class TaggingPromptBuilder:
    """Wraps the engine's prompt builder: same prompt, larger answer budget, persona tag."""

    def __init__(self, original: Any, *, max_tokens: int, temperature: float) -> None:
        self._original = original
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)

    def build_openrouter_prompt_payload(self, **kwargs: Any) -> Dict[str, Any]:
        payload = self._original.build_openrouter_prompt_payload(**kwargs)
        payload["max_tokens"] = self.max_tokens
        payload["temperature"] = self.temperature
        payload["_persona_id"] = getattr(kwargs.get("persona"), "persona_id", None)
        return payload


class CoercingRunManager:
    """Delegates to the engine's run_manager; adds label-to-scale mapping for likert answers."""

    def __init__(self, original: Any, *, enabled: bool = True) -> None:
        self._original = original
        self.enabled = bool(enabled)
        self.likert_labels_mapped = 0
        self._lock = threading.Lock()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)

    def _coerce_openrouter_answer_value(self, question: Any, value: Any) -> Any:
        result = self._original._coerce_openrouter_answer_value(question, value)
        if result is not None or not self.enabled:
            return result
        if question.question_type != "likert" or not isinstance(value, str) or not question.options:
            return None
        options = list(question.options)
        match = self._original._match_survey_option(value, options)
        if match is None:
            return None
        number = options.index(match) + 1
        if question.min_value is not None and number < question.min_value:
            return None
        if question.max_value is not None and number > question.max_value:
            return None
        with self._lock:
            self.likert_labels_mapped += 1
        return number


_TRANSIENT_STATUSES = {408, 429}


class OpenRouterClient:
    """Engine-compatible OpenRouter client with seed, routing, retries, and usage capture.

    Returns the same result dict the engine's client returns ({ok, parsed_json, raw_text, error,
    status_code}) so the adapter's fail-fast and fallback logic apply unchanged. Never raises.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        seed: Optional[int],
        provider_order: Optional[List[str]] = None,
        allow_provider_fallbacks: bool = True,
        max_retries: int = 3,
        retry_base_seconds: float = 2.0,
        json_mode: bool = False,
        reasoning_effort: Optional[str] = None,
        progress_every: int = 10,
        total: Optional[int] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.seed = seed
        self.provider_order = list(provider_order) if provider_order else None
        self.allow_provider_fallbacks = bool(allow_provider_fallbacks)
        self.max_retries = max(0, int(max_retries))
        self.retry_base_seconds = float(retry_base_seconds)
        self.json_mode = bool(json_mode)
        self.reasoning_effort = reasoning_effort
        self.progress_every = max(1, int(progress_every))
        self.total = total
        self.captures: Dict[str, Dict[str, Any]] = {}
        self.stats: Counter = Counter()
        self._lock = threading.Lock()
        self._started = time.monotonic()

    # -- request body -------------------------------------------------------------------------

    def build_body(self, model_name: str, prompt_payload: Dict[str, Any]) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": model_name,
            "messages": prompt_payload.get("messages", []),
            "temperature": prompt_payload.get("temperature", 0.2),
            "max_tokens": prompt_payload.get("max_tokens", 4000),
            "usage": {"include": True},
        }
        if self.seed is not None:
            body["seed"] = int(self.seed)
        if self.provider_order:
            body["provider"] = {"order": self.provider_order, "allow_fallbacks": self.allow_provider_fallbacks}
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.reasoning_effort and self.reasoning_effort != "default":
            body["reasoning"] = {"enabled": False} if self.reasoning_effort == "off" else {"effort": self.reasoning_effort}
        return body

    # -- the call the adapter makes ----------------------------------------------------------

    def generate_survey_response_with_openrouter(
        self, *, model_name: str, prompt_payload: Dict[str, Any], timeout: int = 180
    ) -> Dict[str, Any]:
        payload = dict(prompt_payload)
        persona_id = str(payload.pop("_persona_id", None) or "")
        body = self.build_body(model_name, payload)
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        endpoint = f"{self.base_url}/chat/completions"

        capture: Dict[str, Any] = {
            "persona_id": persona_id,
            "model_requested": model_name,
            "model_served": None,
            "provider": None,
            "generation_id": None,
            "seed": self.seed,
            "status_code": None,
            "attempts": 0,
            "finish_reason": None,
            "latency_ms": None,
            "usage": None,
            "error": None,
            "parsed_ok": False,
            "json_recovered": False,
            "raw_text": "",
        }
        result: Dict[str, Any] = self._failure("no attempt made", None)

        for attempt in range(self.max_retries + 1):
            capture["attempts"] = attempt + 1
            if attempt > 0:
                with self._lock:
                    self.stats["retries"] += 1
                time.sleep(min(30.0, self.retry_base_seconds * (2 ** (attempt - 1))) + random.uniform(0, 0.5))

            started = time.monotonic()
            try:
                response = requests.post(endpoint, headers=headers, json=body, timeout=timeout)
            except requests.Timeout:
                result = self._failure("OpenRouter request timed out.", None)
                capture["error"] = result["error"]
                continue
            except requests.RequestException as exc:
                result = self._failure(f"OpenRouter request error: {exc}", None)
                capture["error"] = result["error"]
                continue
            capture["latency_ms"] = int((time.monotonic() - started) * 1000)
            status = int(response.status_code)
            capture["status_code"] = status

            if status >= 400:
                result = self._failure(f"OpenRouter HTTP {status}", status, raw_text=response.text[:2000])
                capture["error"] = result["error"]
                capture["raw_text"] = response.text[:2000]
                if status in _TRANSIENT_STATUSES or status >= 500:
                    continue
                break  # terminal: the adapter decides whether to stop the run

            try:
                data = response.json()
            except ValueError:
                result = self._failure("OpenRouter returned non-JSON HTTP payload.", status, raw_text=response.text[:4000])
                capture["error"] = result["error"]
                continue

            error_block = data.get("error") if isinstance(data, dict) else None
            if error_block and not (isinstance(data, dict) and data.get("choices")):
                code = error_block.get("code") if isinstance(error_block, dict) else None
                message = error_block.get("message") if isinstance(error_block, dict) else str(error_block)
                try:
                    code_int = int(code) if code is not None else 502
                except (TypeError, ValueError):
                    code_int = 502
                capture["status_code"] = code_int
                result = self._failure(f"OpenRouter error {code_int}: {message}", code_int, raw_text=json.dumps(data)[:2000])
                capture["error"] = result["error"]
                if code_int in _TRANSIENT_STATUSES or code_int >= 500:
                    continue
                break

            capture["model_served"] = data.get("model")
            capture["provider"] = data.get("provider")
            capture["generation_id"] = data.get("id")
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            capture["usage"] = {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cost": usage.get("cost"),
            }
            choices = data.get("choices") or []
            finish_reason = (choices[0] or {}).get("finish_reason") if choices else None
            capture["finish_reason"] = finish_reason
            if finish_reason == "length":
                with self._lock:
                    self.stats["finish_length"] += 1

            raw_text = llm_client._extract_text_content(data)
            capture["raw_text"] = raw_text
            parsed = llm_client._parse_json_strict(raw_text)
            if parsed is None:
                recovered = _recover_json_object(raw_text)
                if recovered is not None:
                    parsed = recovered
                    capture["json_recovered"] = True
            if parsed is None:
                reason = "Model output was truncated (finish_reason=length)." if finish_reason == "length" else "Model output was not valid strict JSON."
                result = self._failure(reason, status, raw_text=raw_text)
                capture["error"] = result["error"]
                continue

            capture["parsed_ok"] = True
            capture["error"] = None
            result = {"ok": True, "parsed_json": parsed, "raw_text": raw_text, "error": None, "status_code": status}
            break

        self._record(capture, result)
        return result

    # -- bookkeeping --------------------------------------------------------------------------

    @staticmethod
    def _failure(error: str, status_code: Optional[int], *, raw_text: str = "") -> Dict[str, Any]:
        return {"ok": False, "parsed_json": None, "raw_text": raw_text, "error": error, "status_code": status_code}

    def _record(self, capture: Dict[str, Any], result: Dict[str, Any]) -> None:
        with self._lock:
            self.captures[capture["persona_id"]] = capture
            self.stats["calls"] += 1
            if result["ok"]:
                self.stats["ok"] += 1
            else:
                self.stats["failed"] += 1
            if capture.get("json_recovered"):
                self.stats["json_recovered"] += 1
            usage = capture.get("usage") or {}
            self.stats["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            self.stats["completion_tokens"] += int(usage.get("completion_tokens") or 0)
            cost = usage.get("cost")
            if isinstance(cost, (int, float)):
                self.stats["usd_reported_micro"] += int(round(float(cost) * 1_000_000))
            done = self.stats["calls"]
            if done % self.progress_every == 0 or (self.total and done == self.total):
                elapsed = time.monotonic() - self._started
                total = f"/{self.total}" if self.total else ""
                print(
                    f"  [{done}{total}] ok={self.stats['ok']} failed={self.stats['failed']} "
                    f"retries={self.stats['retries']} tokens_in={self.stats['prompt_tokens']} "
                    f"tokens_out={self.stats['completion_tokens']} elapsed={elapsed:.0f}s",
                    flush=True,
                )

    @property
    def usd_reported(self) -> float:
        return self.stats["usd_reported_micro"] / 1_000_000


def _recover_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Take the outermost {...} out of prose or a fence the strict parser rejected."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------


def price_for(model: str, price_in: Optional[float], price_out: Optional[float]) -> Tuple[Optional[float], Optional[float], str]:
    if price_in is not None and price_out is not None:
        return float(price_in), float(price_out), "override"
    table = PRICE_TABLE.get(model)
    if table:
        return table[0], table[1], "table"
    return None, None, "unknown"


def estimate_usd(prompt_tokens: int, completion_tokens: int, price_in: Optional[float], price_out: Optional[float]) -> Optional[float]:
    if price_in is None or price_out is None:
        return None
    return round(prompt_tokens * price_in / 1_000_000 + completion_tokens * price_out / 1_000_000, 4)


# ---------------------------------------------------------------------------
# Output files
# ---------------------------------------------------------------------------


def answer_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return str(value)


def respondent_index(respondent_id: str) -> int:
    match = RESPONDENT_ID_PATTERN.search(respondent_id)
    if not match:
        raise ValueError(f"unexpected respondent id {respondent_id!r}")
    return int(match.group(1)) - 1


def git_info() -> Dict[str, Any]:
    def _run(*args: str) -> str:
        try:
            return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return ""

    return {
        "commit": _run("rev-parse", "HEAD"),
        "branch": _run("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(_run("status", "--porcelain", "--untracked-files=no")),
    }


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def write_run_outputs(
    *,
    run_dir: Path,
    run_id: str,
    model: str,
    repeat: int,
    seed: Optional[int],
    survey: Any,
    personas: List[Any],
    records: List[Any],
    record_is_fallback: List[bool],
    captures: Dict[str, Dict[str, Any]],
    prompt_sample: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Write answers_long.csv, answers_wide.csv, questions.csv, raw_responses.jsonl, prompt_sample.txt.

    Returns per-persona fallback counts and the wide rows for the summary.
    """
    question_ids = [question.id for question in survey.questions]
    persona_ids = [persona.persona_id for persona in personas]

    long_path = run_dir / "answers_long.csv"
    wide_rows: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    fallback_per_persona: Counter = Counter()
    with open(long_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["run_id", "model", "repeat", "seed", "persona_id", "respondent_id", "question_id", "question_type", "answer", "answer_json", "is_fallback"]
        )
        for record, is_fallback in zip(records, record_is_fallback):
            pid = persona_ids[respondent_index(record.respondent_id) % len(persona_ids)]
            writer.writerow(
                [
                    run_id,
                    record.model,
                    repeat,
                    "" if seed is None else seed,
                    pid,
                    record.respondent_id,
                    record.question_id,
                    record.question_type,
                    answer_scalar(record.answer),
                    json.dumps(record.answer, ensure_ascii=False),
                    "true" if is_fallback else "false",
                ]
            )
            row = wide_rows.setdefault(
                pid,
                {"run_id": run_id, "model": record.model, "repeat": repeat, "seed": "" if seed is None else seed, "persona_id": pid, "respondent_id": record.respondent_id},
            )
            row[record.question_id] = answer_scalar(record.answer)
            if is_fallback:
                fallback_per_persona[pid] += 1

    wide_path = run_dir / "answers_wide.csv"
    with open(wide_path, "w", newline="", encoding="utf-8") as handle:
        header = ["run_id", "model", "repeat", "seed", "persona_id", "respondent_id", *question_ids, "n_fallback", "all_live"]
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for pid, row in wide_rows.items():
            row["n_fallback"] = fallback_per_persona.get(pid, 0)
            row["all_live"] = "true" if fallback_per_persona.get(pid, 0) == 0 else "false"
            writer.writerow({key: row.get(key, "") for key in header})

    with open(run_dir / "questions.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["question_id", "question_type", "min_value", "max_value", "options", "text"])
        for question in survey.questions:
            writer.writerow(
                [
                    question.id,
                    question.question_type,
                    "" if question.min_value is None else question.min_value,
                    "" if question.max_value is None else question.max_value,
                    "|".join(str(option) for option in (question.options or [])),
                    question.text,
                ]
            )

    with open(run_dir / "raw_responses.jsonl", "w", encoding="utf-8") as handle:
        for pid in persona_ids:
            capture = captures.get(pid)
            if capture is None:
                capture = {"persona_id": pid, "error": "no response captured"}
            handle.write(json.dumps(capture, ensure_ascii=False, default=str) + "\n")

    if prompt_sample:
        lines = []
        for message in prompt_sample.get("messages", []):
            lines.append(f"--- {message.get('role', '?').upper()} ---")
            lines.append(str(message.get("content", "")))
            lines.append("")
        lines.append(f"temperature={prompt_sample.get('temperature')} max_tokens={prompt_sample.get('max_tokens')}")
        (run_dir / "prompt_sample.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"fallback_per_persona": dict(fallback_per_persona), "wide_rows": list(wide_rows.values())}


# ---------------------------------------------------------------------------
# Sanity summary
# ---------------------------------------------------------------------------


def _parse_bucket_bounds(option: str) -> Optional[Tuple[float, float]]:
    """Turn '25–34', '$100,000–$149,999', 'Under 25', '$200,000 or more' into (low, high)."""
    text = option.lower().replace(",", "").replace("$", "")
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return None
    if any(word in text for word in ("under", "less than", "below")) and len(numbers) == 1:
        return (float("-inf"), numbers[0] - 1e-9)
    if any(word in text for word in ("or more", "or older", "and above", "and over", "+", "over", "above")) and len(numbers) == 1:
        return (numbers[0], float("inf"))
    if len(numbers) >= 2:
        return (min(numbers[:2]), max(numbers[:2]))
    return None


def bucket_for(value: Optional[float], options: Iterable[str]) -> Optional[str]:
    if value is None:
        return None
    for option in options:
        bounds = _parse_bucket_bounds(str(option))
        if bounds and bounds[0] <= value <= bounds[1]:
            return str(option)
    return None


def summarize_wide_rows(
    *,
    wide_rows: List[Dict[str, Any]],
    survey: Any,
    census_lookup: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    questions = {question.id: question for question in survey.questions}
    total = len(wide_rows)
    summary: Dict[str, Any] = {"respondents": total}

    def distribution(question_id: str) -> Dict[str, float]:
        counts = Counter(str(row.get(question_id, "")) for row in wide_rows)
        return {key: round(value / total, 4) for key, value in sorted(counts.items())} if total else {}

    for question_id in ("Q1", "Q2", "Q6", "Q14"):
        if question_id in questions:
            summary[f"{question_id}_distribution"] = distribution(question_id)

    if "Q30" in questions:
        expected = next((option for option in (questions["Q30"].options or []) if "moderately" in str(option).lower()), None)
        passed = sum(1 for row in wide_rows if expected is not None and str(row.get("Q30", "")) == str(expected))
        summary["Q30_attention_check"] = {"expected": expected, "pass_rate": round(passed / total, 4) if total else None}

    for question_id, census_key in (("Q21", "exact_age"), ("Q22", "exact_household_income")):
        if question_id not in questions:
            continue
        options = list(questions[question_id].options or [])
        checked = agreed = 0
        for row in wide_rows:
            census = census_lookup.get(row["persona_id"]) or {}
            expected_bucket = bucket_for(census.get(census_key), options)
            if expected_bucket is None:
                continue
            checked += 1
            if str(row.get(question_id, "")) == expected_bucket:
                agreed += 1
        summary[f"{question_id}_consistency_with_{census_key}"] = {"checked": checked, "agreement_rate": round(agreed / checked, 4) if checked else None}

    summary["respondents_with_any_fallback"] = sum(1 for row in wide_rows if str(row.get("all_live", "true")) == "false")
    return summary


def render_summary_markdown(run_id: str, summary: Dict[str, Any]) -> str:
    lines = [f"# Summary — {run_id}", ""]
    lines.append(f"- Respondents: {summary.get('respondents')}")
    lines.append(f"- Respondents with any fabricated answer: {summary.get('respondents_with_any_fallback')}")
    attention = summary.get("Q30_attention_check") or {}
    lines.append(f"- Q30 attention check (expected {attention.get('expected')!r}): pass rate {attention.get('pass_rate')}")
    for key in ("Q21_consistency_with_exact_age", "Q22_consistency_with_exact_household_income"):
        item = summary.get(key) or {}
        lines.append(f"- {key}: {item.get('agreement_rate')} over {item.get('checked')} checked")
    for key in ("Q1_distribution", "Q2_distribution", "Q6_distribution", "Q14_distribution"):
        dist = summary.get(key)
        if dist:
            lines.append("")
            lines.append(f"## {key}")
            lines.append("")
            lines.append("| answer | share |")
            lines.append("| --- | --- |")
            for answer, share in dist.items():
                lines.append(f"| {answer} | {share:.1%} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------


def check_guardrails(*, generation_debug: Dict[str, Any], expected_respondents: int, fallback_threshold: float) -> List[str]:
    reasons: List[str] = []
    if int(generation_debug.get("provider_error_count") or 0) > 0:
        reasons.append(f"provider_error_count={generation_debug.get('provider_error_count')}")
    if int(generation_debug.get("request_errors") or 0) > 0:
        reasons.append(f"request_errors={generation_debug.get('request_errors')}")
    answers = int(generation_debug.get("answer_records") or 0)
    fallback = int(generation_debug.get("questions_fallback_to_mock") or 0)
    share = (fallback / answers) if answers else 1.0
    if share > fallback_threshold:
        reasons.append(f"fallback_share={share:.4f} exceeds {fallback_threshold}")
    if int(generation_debug.get("executions") or 0) != expected_respondents:
        reasons.append(f"executions={generation_debug.get('executions')} != personas={expected_respondents}")
    return reasons


def append_index_row(index_path: Path, row: Dict[str, Any]) -> None:
    header = [
        "run_id", "status", "model", "repeat", "seed", "prompt_variant", "limit", "respondents", "answers",
        "fallback_answers", "fallback_share", "request_errors", "provider_error_count", "prompt_tokens",
        "completion_tokens", "usd_reported", "usd_estimated", "started_at", "finished_at", "duration_sec",
        "git_commit", "run_dir",
    ]
    exists = index_path.exists()
    with open(index_path, "a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        if not exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in header})


def run_one(
    *,
    model: str,
    repeat: int,
    seed: Optional[int],
    personas: List[Any],
    survey: Any,
    contexts: Tuple[Any, Any],
    args: argparse.Namespace,
    client: Optional[Any] = None,
    census_lookup: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run one model once over all personas. Returns the manifest dict (status completed|failed)."""
    started = utcnow()
    run_id = make_run_id(model, repeat, limit=args.limit, tag=args.run_tag, now=started)
    out_dir = Path(args.out_dir)
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    product, market = contexts
    price_in, price_out, price_source = price_for(model, args.price_in, args.price_out)
    git = git_info()

    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "started_at": started.isoformat(),
        "finished_at": None,
        "duration_sec": None,
        "script": {"path": str(Path(__file__).resolve().relative_to(REPO_ROOT)), "git_commit": git["commit"], "git_branch": git["branch"], "git_dirty": git["dirty"], "python": sys.version.split()[0]},
        "model": {"requested": model, "served_counts": {}, "provider_counts": {}},
        "provider_routing": {"order": args.provider_order, "allow_fallbacks": not args.no_provider_fallbacks},
        "json_mode": bool(args.json_mode),
        "reasoning_effort": args.reasoning_effort,
        "seed": seed,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "timeout_sec": args.timeout,
        "max_retries": args.max_retries,
        "concurrency": args.concurrency,
        "prompt_variant": args.prompt_variant,
        "likert_label_map": not args.no_likert_label_map,
        "prompt_builder": "backend.simulation.prompt_builder.build_openrouter_prompt_payload",
        "survey": {"path": str(args.survey), "sha256": sha256_of_file(Path(args.survey)), "title": survey.survey_title, "question_count": len(survey.questions), "question_ids": [q.id for q in survey.questions]},
        "personas": {"path": str(args.personas), "sha256": sha256_of_file(Path(args.personas)), "rows_used": len(personas), "limit": args.limit, "first_id": personas[0].persona_id, "last_id": personas[-1].persona_id},
        "context": {"business_product": "backend.presets.get_neo_business_product_defaults", "market": "backend.presets.get_neo_market_defaults", "audience_filter": None, "context_sha256": sha256_of_text(json.dumps({"product": product.model_dump(), "market": market.model_dump()}, sort_keys=True, default=str))},
        "generation_debug": None,
        "counts": None,
        "tokens": None,
        "cost": {"usd_reported": None, "usd_estimated": None, "price_in_per_m": price_in, "price_out_per_m": price_out, "price_source": price_source},
        "guardrails": {"fallback_threshold": args.fallback_threshold, "passed": None, "reasons": []},
        "outputs": {},
        "error": None,
        "exit_code": None,
    }
    write_json(run_dir / "manifest.json", manifest)

    builder = TaggingPromptBuilder(prompt_builder, max_tokens=args.max_tokens, temperature=args.temperature)
    manager = CoercingRunManager(run_manager, enabled=not args.no_likert_label_map)
    if client is None:
        client = OpenRouterClient(
            api_key=env_value("OPENROUTER_API_KEY", "") or "",
            base_url=env_value("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1") or "https://openrouter.ai/api/v1",
            seed=seed,
            provider_order=args.provider_order,
            allow_provider_fallbacks=not args.no_provider_fallbacks,
            max_retries=args.max_retries,
            json_mode=args.json_mode,
            reasoning_effort=args.reasoning_effort,
            progress_every=args.progress_every,
            total=len(personas),
        )
    config = build_config(run_id=run_id, survey=survey, personas=personas, model=model, notes="research/neo_persona_set phase2 headless run")
    prompt_sample = builder.build_openrouter_prompt_payload(
        persona=personas[0], survey_schema=survey, business_product_context=product, market_context=market, audience_filter=None
    )

    print(f"\n=== {run_id}: {len(personas)} personas x {len(survey.questions)} questions on {model} (seed={seed}, concurrency={args.concurrency}) ===", flush=True)
    status = "failed"
    exit_code = 2
    records: List[Any] = []
    record_is_fallback: List[bool] = []
    generation_debug: Dict[str, Any] = {}
    try:
        records, generation_debug, record_is_fallback = domain._generate_live_response_records_with_debug(
            schemas=schemas,
            run_manager=manager,
            llm_client=client,
            prompt_builder=builder,
            config=config,
            survey_schema=survey,
            audience_filter=None,
            persona_profiles=personas,
            business_product_context=product,
            market_context=market,
            prompt_user_template_override=None,
            openrouter_timeout_sec=args.timeout,
            max_concurrency=args.concurrency,
        )
        reasons = check_guardrails(generation_debug=generation_debug, expected_respondents=len(personas), fallback_threshold=args.fallback_threshold)
        if not reasons:
            status = "completed"
            exit_code = 0
        manifest["guardrails"]["passed"] = not reasons
        manifest["guardrails"]["reasons"] = reasons
    except KeyboardInterrupt:
        manifest["error"] = "interrupted"
        exit_code = 130
        print("\nInterrupted; writing partial output.", file=sys.stderr)
    except ApiError as exc:
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        print(f"\nProvider stopped the run: {manifest['error']}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — keep the partial output no matter what failed
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        print(f"\nRun failed: {manifest['error']}", file=sys.stderr)

    finished = utcnow()
    outputs_info: Dict[str, Any] = {"fallback_per_persona": {}, "wide_rows": []}
    if records:
        outputs_info = write_run_outputs(
            run_dir=run_dir, run_id=run_id, model=model, repeat=repeat, seed=seed, survey=survey, personas=personas,
            records=records, record_is_fallback=record_is_fallback, captures=getattr(client, "captures", {}), prompt_sample=prompt_sample,
        )
    else:
        # Nothing assembled (terminal error mid-batch): keep whatever the client captured for audit.
        with open(run_dir / "raw_responses.jsonl", "w", encoding="utf-8") as handle:
            for capture in getattr(client, "captures", {}).values():
                handle.write(json.dumps(capture, ensure_ascii=False, default=str) + "\n")
    write_json(run_dir / "generation_debug.json", generation_debug)

    captures = getattr(client, "captures", {})
    stats = getattr(client, "stats", Counter())
    prompt_tokens = int(stats.get("prompt_tokens", 0))
    completion_tokens = int(stats.get("completion_tokens", 0))
    answers = int(generation_debug.get("answer_records") or 0)
    fallback = int(generation_debug.get("questions_fallback_to_mock") or 0)
    manifest["model"]["served_counts"] = dict(Counter(str(c.get("model_served")) for c in captures.values() if c.get("model_served")))
    manifest["model"]["provider_counts"] = dict(Counter(str(c.get("provider")) for c in captures.values() if c.get("provider")))
    manifest["generation_debug"] = generation_debug
    manifest["counts"] = {
        "respondents": int(generation_debug.get("executions") or 0),
        "answers": answers,
        "live_answers": int(generation_debug.get("questions_parsed_from_live") or 0),
        "fallback_answers": fallback,
        "fallback_share": round(fallback / answers, 6) if answers else None,
        "respondents_with_any_fallback": sum(1 for v in outputs_info["fallback_per_persona"].values() if v),
        "request_errors": int(generation_debug.get("request_errors") or 0),
        "provider_error_count": int(generation_debug.get("provider_error_count") or 0),
        "malformed_json_count": int(generation_debug.get("malformed_json_count") or 0),
        "retries_total": int(stats.get("retries", 0)),
        "json_recovered": int(stats.get("json_recovered", 0)),
        "likert_labels_mapped": int(manager.likert_labels_mapped),
        "finish_reason_length": int(stats.get("finish_length", 0)),
    }
    respondents = manifest["counts"]["respondents"] or len(captures) or 1
    manifest["tokens"] = {
        "prompt": prompt_tokens,
        "completion": completion_tokens,
        "total": prompt_tokens + completion_tokens,
        "mean_prompt_per_respondent": round(prompt_tokens / respondents, 1),
        "mean_completion_per_respondent": round(completion_tokens / respondents, 1),
    }
    usd_reported = getattr(client, "usd_reported", None)
    manifest["cost"]["usd_reported"] = round(usd_reported, 4) if isinstance(usd_reported, (int, float)) and usd_reported else None
    manifest["cost"]["usd_estimated"] = estimate_usd(prompt_tokens, completion_tokens, price_in, price_out)

    summary: Dict[str, Any] = {}
    if outputs_info["wide_rows"]:
        summary = summarize_wide_rows(wide_rows=outputs_info["wide_rows"], survey=survey, census_lookup=census_lookup or {})
        (run_dir / "summary.md").write_text(render_summary_markdown(run_id, summary), encoding="utf-8")
        manifest["summary"] = summary

    manifest["status"] = status
    manifest["exit_code"] = exit_code
    manifest["finished_at"] = finished.isoformat()
    manifest["duration_sec"] = round((finished - started).total_seconds(), 1)
    manifest["outputs"] = {p.name: sha256_of_file(p) for p in sorted(run_dir.iterdir()) if p.is_file() and p.name != "manifest.json"}
    write_json(run_dir / "manifest.json", manifest)

    final_dir = run_dir
    if status != "completed":
        final_dir = out_dir / f"{run_id}_failed"
        shutil.move(str(run_dir), str(final_dir))
    manifest["run_dir"] = str(final_dir)

    append_index_row(
        out_dir / "index.csv",
        {
            "run_id": run_id, "status": status, "model": model, "repeat": repeat, "seed": seed, "prompt_variant": args.prompt_variant,
            "limit": args.limit if args.limit is not None else "", "respondents": manifest["counts"]["respondents"], "answers": answers,
            "fallback_answers": fallback, "fallback_share": manifest["counts"]["fallback_share"], "request_errors": manifest["counts"]["request_errors"],
            "provider_error_count": manifest["counts"]["provider_error_count"], "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "usd_reported": manifest["cost"]["usd_reported"], "usd_estimated": manifest["cost"]["usd_estimated"], "started_at": manifest["started_at"],
            "finished_at": manifest["finished_at"], "duration_sec": manifest["duration_sec"], "git_commit": git["commit"], "run_dir": str(final_dir),
        },
    )

    print(
        f"--- {run_id}: {status.upper()} | respondents={manifest['counts']['respondents']} answers={answers} "
        f"fallback={fallback} retries={manifest['counts']['retries_total']} tokens={prompt_tokens}/{completion_tokens} "
        f"usd~{manifest['cost']['usd_estimated']} reported={manifest['cost']['usd_reported']} in {manifest['duration_sec']}s -> {final_dir}",
        flush=True,
    )
    if manifest["guardrails"]["reasons"]:
        print(f"    guardrails: {manifest['guardrails']['reasons']}", flush=True)
    if summary:
        attention = summary.get("Q30_attention_check") or {}
        print(f"    Q30 attention pass rate={attention.get('pass_rate')} Q1={summary.get('Q1_distribution')}", flush=True)
    return manifest


# ---------------------------------------------------------------------------
# Dry run and cross-run summary
# ---------------------------------------------------------------------------


def dry_run(*, personas: List[Any], survey: Any, contexts: Tuple[Any, Any], args: argparse.Namespace) -> int:
    product, market = contexts
    builder = TaggingPromptBuilder(prompt_builder, max_tokens=args.max_tokens, temperature=args.temperature)
    payload = builder.build_openrouter_prompt_payload(
        persona=personas[0], survey_schema=survey, business_product_context=product, market_context=market, audience_filter=None
    )
    chars = sum(len(str(m.get("content", ""))) for m in payload["messages"])
    est_in = chars // 4
    est_out = 900
    print(f"personas: {len(personas)} (variant={args.prompt_variant})  questions: {len(survey.questions)}")
    print("question ids:", ", ".join(q.id for q in survey.questions))
    print(f"prompt for {personas[0].persona_id}: {chars} chars ≈ {est_in} input tokens; assuming ≈{est_out} output tokens")
    print()
    for message in payload["messages"]:
        print(f"--- {message['role'].upper()} ---")
        print(message["content"])
        print()
    print(f"temperature={payload['temperature']} max_tokens={payload['max_tokens']} seed_base={args.seed_base}")
    print()
    print("projected cost per run (list prices):")
    total = 0.0
    for model in args.models:
        price_in, price_out, source = price_for(model, args.price_in, args.price_out)
        usd = estimate_usd(est_in * len(personas), est_out * len(personas), price_in, price_out)
        total += usd or 0.0
        print(f"  {model:36s} {source:9s} ~${usd} per run x {args.repeats} repeats")
    print(f"  total for {len(args.models)} model(s) x {args.repeats} repeat(s): ~${round(total * args.repeats, 2)}")
    return 0


def cross_run_summary(run_ids: List[str], *, out_dir: Path, survey: Any, census_lookup: Dict[str, Dict[str, Any]]) -> str:
    runs: Dict[str, List[Dict[str, Any]]] = {}
    manifests: Dict[str, Dict[str, Any]] = {}
    for run_id in run_ids:
        run_dir = out_dir / run_id
        if not run_dir.exists():
            run_dir = out_dir / f"{run_id}_failed"
        wide_path = run_dir / "answers_wide.csv"
        if not wide_path.exists():
            print(f"skip {run_id}: no answers_wide.csv", file=sys.stderr)
            continue
        with open(wide_path, newline="", encoding="utf-8") as handle:
            runs[run_id] = list(csv.DictReader(handle))
        manifest_path = run_dir / "manifest.json"
        manifests[run_id] = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    lines = ["# Cross-run summary", ""]
    per_run: Dict[str, Dict[str, Any]] = {}
    for run_id, rows in runs.items():
        summary = summarize_wide_rows(wide_rows=rows, survey=survey, census_lookup=census_lookup)
        per_run[run_id] = summary
        model = manifests.get(run_id, {}).get("model", {}).get("requested", "?")
        cost = manifests.get(run_id, {}).get("cost", {})
        lines.append(f"## {run_id}")
        lines.append("")
        lines.append(f"- model: {model}; respondents: {summary['respondents']}; usd est {cost.get('usd_estimated')} / reported {cost.get('usd_reported')}")
        attention = summary.get("Q30_attention_check") or {}
        lines.append(f"- Q30 attention pass rate: {attention.get('pass_rate')}")
        for key in ("Q21_consistency_with_exact_age", "Q22_consistency_with_exact_household_income"):
            item = summary.get(key) or {}
            lines.append(f"- {key}: {item.get('agreement_rate')} ({item.get('checked')} checked)")
        lines.append(f"- Q1 distribution: {summary.get('Q1_distribution')}")
        lines.append("")

    # Repeat-to-repeat agreement within a model.
    by_model: Dict[str, List[str]] = {}
    for run_id in runs:
        model = manifests.get(run_id, {}).get("model", {}).get("requested", "?")
        by_model.setdefault(model, []).append(run_id)
    likert_ids = [q.id for q in survey.questions if q.question_type == "likert"]
    question_ids = [q.id for q in survey.questions]
    for model, ids in by_model.items():
        if len(ids) < 2:
            continue
        lines.append(f"## Repeat agreement — {model}")
        lines.append("")
        lines.append("| pair | exact agreement (all questions) | mean abs diff (likert) | Q1 share diff (max over answers) |")
        lines.append("| --- | --- | --- | --- |")
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a = {row["persona_id"]: row for row in runs[ids[i]]}
                b = {row["persona_id"]: row for row in runs[ids[j]]}
                shared = [pid for pid in a if pid in b]
                agree = compared = 0
                diffs: List[float] = []
                for pid in shared:
                    for qid in question_ids:
                        compared += 1
                        if a[pid].get(qid, "") == b[pid].get(qid, ""):
                            agree += 1
                    for qid in likert_ids:
                        try:
                            diffs.append(abs(float(a[pid].get(qid)) - float(b[pid].get(qid))))
                        except (TypeError, ValueError):
                            continue
                dist_a = per_run[ids[i]].get("Q1_distribution") or {}
                dist_b = per_run[ids[j]].get("Q1_distribution") or {}
                q1_diff = max((abs(dist_a.get(k, 0) - dist_b.get(k, 0)) for k in set(dist_a) | set(dist_b)), default=0.0)
                lines.append(
                    f"| {ids[i]} vs {ids[j]} | {agree / compared:.1%} | {sum(diffs) / len(diffs) if diffs else float('nan'):.3f} | {q1_diff:.1%} |"
                )
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--personas", type=Path, default=DEFAULT_PERSONAS)
    parser.add_argument("--survey", type=Path, default=DEFAULT_SURVEY)
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None, help="use only the first N personas (smoke test)")
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--concurrency", type=int, default=int(env_value("SIMULATION_MAX_CONCURRENCY", "8") or 8))
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--provider-order", type=lambda s: [p.strip() for p in s.split(",") if p.strip()], default=None)
    parser.add_argument("--no-provider-fallbacks", action="store_true")
    parser.add_argument("--price-in", type=float, default=None, help="USD per million input tokens (override)")
    parser.add_argument("--price-out", type=float, default=None, help="USD per million output tokens (override)")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--seed-base", type=int, default=DEFAULT_SEED_BASE, help="seed = seed_base*10 + repeat")
    parser.add_argument("--prompt-variant", choices=PROMPT_VARIANTS, default="full")
    parser.add_argument("--json-mode", action="store_true", help="send response_format=json_object (not all providers accept it)")
    parser.add_argument("--reasoning-effort", choices=["off", "low", "medium", "high", "default"], default="off",
                        help="hidden reasoning; both suggested models think for ~3,000 tokens per persona unless this is off")
    parser.add_argument("--no-likert-label-map", action="store_true")
    parser.add_argument("--fallback-threshold", type=float, default=0.01)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-tag", default=None)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary", nargs="+", default=None, metavar="RUN_ID", help="summarize existing runs instead of running")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    args.personas = assert_not_real_data(args.personas, "--personas")
    args.survey = assert_not_real_data(args.survey, "--survey")
    args.out_dir = assert_not_real_data(args.out_dir, "--out-dir")
    args.concurrency = max(1, min(int(args.concurrency), 32))

    survey = load_survey(args.survey)
    census_lookup = persona_census_lookup(args.personas)

    if args.summary:
        text = cross_run_summary(args.summary, out_dir=args.out_dir, survey=survey, census_lookup=census_lookup)
        print(text)
        (args.out_dir / "cross_run_summary.md").write_text(text, encoding="utf-8")
        return 0

    personas = load_personas(args.personas, limit=args.limit, prompt_variant=args.prompt_variant)
    contexts = load_contexts()
    if args.dry_run:
        return dry_run(personas=personas, survey=survey, contexts=contexts, args=args)

    if not env_value("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is not set (apps/api/.env or environment).", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    outcomes: List[Dict[str, Any]] = []
    for model in args.models:
        for repeat in range(1, int(args.repeats) + 1):
            seed = int(args.seed_base) * 10 + repeat
            manifest = run_one(
                model=model, repeat=repeat, seed=seed, personas=personas, survey=survey, contexts=contexts, args=args, census_lookup=census_lookup
            )
            outcomes.append(manifest)
            if manifest["status"] != "completed" and not args.continue_on_failure:
                print(f"Stopping after failed run {manifest['run_id']} (use --continue-on-failure to keep going).", file=sys.stderr)
                return int(manifest.get("exit_code") or 2)

    print("\n=== runs ===")
    for manifest in outcomes:
        print(f"{manifest['status']:9s} {manifest['run_id']}  usd~{manifest['cost']['usd_estimated']}  fallback={manifest['counts']['fallback_answers']}")
    return 0 if all(m["status"] == "completed" for m in outcomes) else 2


if __name__ == "__main__":
    raise SystemExit(main())
