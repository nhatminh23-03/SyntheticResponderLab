#!/usr/bin/env python3
"""Measure 30 concurrent, zero-cost requests to the interview endpoint.

Run from the repository root after pre-warming the interview cache:

    python scripts/load_check.py

Cache misses are sent with an estimate above the class run budget, so the API
rejects them during preflight before contacting the provider. Only responses
that explicitly report a cache hit and zero session cost count as successes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = REPO_ROOT / "apps/api"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(API_ROOT))

from scripts.prewarm_cache import SUGGESTED_QUESTIONS  # noqa: E402
from src.persistence.persona_seed import EXPECTED_PERSONA_COUNT  # noqa: E402
from src.services.model_catalog import DEFAULT_INTERVIEW_MODEL_ID  # noqa: E402


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 30.0
CLASS_SIZE = EXPECTED_PERSONA_COUNT
# This value is deliberately above the $0.75 run budget. A cache miss enters
# provider preflight and is rejected before any paid call can begin.
CACHE_MISS_GUARD_USD = "1000000"


class LoadCheckHttpError(RuntimeError):
    """Raised when the API cannot return a successful JSON response."""


@dataclass(frozen=True)
class RequestResult:
    student_number: int
    persona_id: str
    latency_ms: float
    error: str | None

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class LoadSummary:
    request_count: int
    success_count: int
    error_count: int
    error_rate_percent: float
    p50_ms: float
    p95_ms: float
    p99_ms: float


JsonRequester = Callable[..., dict[str, object]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Send 30 concurrent, cache-only-safe requests to the standalone "
            "interview endpoint and report latency percentiles and error rate."
        )
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"FastAPI origin (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--study-id",
        default=None,
        help="Use an existing study instead of creating one for the check.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS:g}).",
    )
    parser.add_argument(
        "--deployment-secret",
        default=os.environ.get("DEPLOYMENT_SHARED_SECRET", ""),
        help="Backend deployment secret; defaults to DEPLOYMENT_SHARED_SECRET.",
    )
    parser.add_argument(
        "--user-id",
        default="load-check",
        help="Synthetic owner id used for setup and all requests (default: load-check).",
    )
    return parser


def _api_headers(*, deployment_secret: str, user_id: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Authenticated-User-Id": user_id,
        "X-Authenticated-Auth-Mode": "load-check",
    }
    if deployment_secret:
        headers["X-Deployment-Secret"] = deployment_secret
    return headers


def _error_message(payload: object) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    return str(payload)


def request_json(
    url: str,
    *,
    method: str,
    headers: Mapping[str, str],
    timeout: float,
    payload: Mapping[str, object] | None = None,
) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers=dict(headers),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            decoded = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            decoded_error = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            decoded_error = exc.reason
        raise LoadCheckHttpError(
            f"HTTP {exc.code}: {_error_message(decoded_error)}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LoadCheckHttpError(str(exc)) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LoadCheckHttpError("API returned a non-JSON response.") from exc

    if not isinstance(decoded, dict):
        raise LoadCheckHttpError("API returned JSON that was not an object.")
    return decoded


def build_interview_payload(persona_id: str, student_number: int) -> dict[str, object]:
    return {
        "persona_id": persona_id,
        "prompt": SUGGESTED_QUESTIONS[(student_number - 1) % len(SUGGESTED_QUESTIONS)],
        "messages": [],
        "model": DEFAULT_INTERVIEW_MODEL_ID,
        "session_id": f"load-check-{uuid.uuid4().hex}-{student_number:02d}",
        "estimated_run_cost_usd": CACHE_MISS_GUARD_USD,
        "standalone": True,
        "allow_expensive_models": False,
    }


def validate_cached_response(payload: Mapping[str, object]) -> str | None:
    data = payload.get("data")
    chat = data.get("interview_chat") if isinstance(data, dict) else None
    if not isinstance(chat, dict):
        return "response did not include data.interview_chat"
    if chat.get("cache_hit") is not True:
        return "response was not a cache hit"

    usage = chat.get("session_usage")
    cost = usage.get("cost_usd") if isinstance(usage, dict) else None
    try:
        parsed_cost = Decimal(str(cost))
    except (InvalidOperation, ValueError):
        return "response did not include a valid session cost"
    if parsed_cost != 0:
        return f"response reported non-zero session cost ${parsed_cost}"
    return None


def _hit_interview(
    *,
    student_number: int,
    persona_id: str,
    endpoint: str,
    headers: Mapping[str, str],
    timeout: float,
    start_barrier: threading.Barrier,
    requester: JsonRequester,
) -> RequestResult:
    try:
        start_barrier.wait(timeout=timeout)
    except threading.BrokenBarrierError:
        return RequestResult(student_number, persona_id, 0.0, "concurrency barrier failed")

    started = time.perf_counter()
    try:
        response = requester(
            endpoint,
            method="POST",
            headers=headers,
            timeout=timeout,
            payload=build_interview_payload(persona_id, student_number),
        )
        error = validate_cached_response(response)
    except Exception as exc:  # Each failed student request belongs in the error rate.
        error = str(exc) or exc.__class__.__name__
    latency_ms = (time.perf_counter() - started) * 1000
    return RequestResult(student_number, persona_id, latency_ms, error)


def run_concurrent_requests(
    *,
    base_url: str,
    study_id: str,
    persona_ids: Sequence[str],
    headers: Mapping[str, str],
    timeout: float,
    requester: JsonRequester = request_json,
) -> list[RequestResult]:
    if len(persona_ids) != CLASS_SIZE:
        raise ValueError(f"Load check requires exactly {CLASS_SIZE} personas.")

    endpoint = f"{base_url.rstrip('/')}/api/v1/studies/{study_id}/interview/chat"
    start_barrier = threading.Barrier(CLASS_SIZE)
    with ThreadPoolExecutor(max_workers=CLASS_SIZE) as executor:
        futures = [
            executor.submit(
                _hit_interview,
                student_number=index,
                persona_id=persona_id,
                endpoint=endpoint,
                headers=headers,
                timeout=timeout,
                start_barrier=start_barrier,
                requester=requester,
            )
            for index, persona_id in enumerate(persona_ids, start=1)
        ]
    return sorted((future.result() for future in futures), key=lambda item: item.student_number)


def nearest_rank_percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        raise ValueError("Cannot calculate a percentile without values.")
    if percentile < 1 or percentile > 100:
        raise ValueError("Percentile must be between 1 and 100.")
    ordered = sorted(values)
    rank = math.ceil((percentile / 100) * len(ordered))
    return ordered[rank - 1]


def summarize_results(results: Sequence[RequestResult]) -> LoadSummary:
    if not results:
        raise ValueError("Cannot summarize an empty load check.")
    latencies = [result.latency_ms for result in results]
    error_count = sum(not result.succeeded for result in results)
    request_count = len(results)
    return LoadSummary(
        request_count=request_count,
        success_count=request_count - error_count,
        error_count=error_count,
        error_rate_percent=(error_count / request_count) * 100,
        p50_ms=nearest_rank_percentile(latencies, 50),
        p95_ms=nearest_rank_percentile(latencies, 95),
        p99_ms=nearest_rank_percentile(latencies, 99),
    )


def _extract_study_id(payload: Mapping[str, object]) -> str:
    data = payload.get("data")
    study = data.get("study") if isinstance(data, dict) else None
    study_id = study.get("study_id") if isinstance(study, dict) else None
    if not study_id:
        raise LoadCheckHttpError(
            "Study creation response did not include data.study.study_id."
        )
    return str(study_id)


def _extract_persona_ids(payload: Mapping[str, object]) -> list[str]:
    data = payload.get("data")
    personas = data.get("personas") if isinstance(data, dict) else None
    if not isinstance(personas, list):
        raise LoadCheckHttpError("Persona response did not include data.personas.")
    persona_ids = [
        str(persona["persona_id"])
        for persona in personas
        if isinstance(persona, dict) and persona.get("persona_id")
    ]
    if len(persona_ids) != CLASS_SIZE:
        raise LoadCheckHttpError(
            f"Load check requires exactly {CLASS_SIZE} database personas; "
            f"the API returned {len(persona_ids)}."
        )
    return persona_ids


def run(args: argparse.Namespace, *, requester: JsonRequester = request_json) -> int:
    if args.timeout <= 0:
        print("Refusing to run: --timeout must be positive.", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    headers = _api_headers(
        deployment_secret=args.deployment_secret.strip(),
        user_id=args.user_id.strip() or "load-check",
    )
    try:
        requester(
            f"{base_url}/api/v1/health",
            method="GET",
            headers=headers,
            timeout=args.timeout,
        )
    except LoadCheckHttpError as exc:
        print(f"No local API server is reachable at {base_url}: {exc}", file=sys.stderr)
        print(
            "Start it with `cd apps/api && CACHE_MODE=replay_only "
            "uvicorn src.main:app --port 8000`, then rerun this command.",
            file=sys.stderr,
        )
        return 2

    try:
        personas_payload = requester(
            f"{base_url}/api/v1/personas",
            method="GET",
            headers=headers,
            timeout=args.timeout,
        )
        persona_ids = _extract_persona_ids(personas_payload)
        if args.study_id:
            study_id = args.study_id
        else:
            study_payload = requester(
                f"{base_url}/api/v1/studies",
                method="POST",
                headers=headers,
                timeout=args.timeout,
                payload={"study_mode": "neo_smart"},
            )
            study_id = _extract_study_id(study_payload)
    except LoadCheckHttpError as exc:
        print(f"Load-check setup failed: {exc}", file=sys.stderr)
        return 2

    print(f"Target: {base_url}")
    print(f"Study: {study_id}")
    print(f"Concurrent students: {CLASS_SIZE}")
    print(
        "Cost guard: only zero-cost cache hits pass; cache misses are blocked "
        "before provider calls."
    )
    results = run_concurrent_requests(
        base_url=base_url,
        study_id=study_id,
        persona_ids=persona_ids,
        headers=headers,
        timeout=args.timeout,
        requester=requester,
    )
    summary = summarize_results(results)

    print(f"p50 latency: {summary.p50_ms:.1f} ms")
    print(f"p95 latency: {summary.p95_ms:.1f} ms")
    print(f"p99 latency: {summary.p99_ms:.1f} ms")
    print(
        f"Error rate: {summary.error_rate_percent:.1f}% "
        f"({summary.error_count}/{summary.request_count})"
    )
    if summary.error_count:
        print("Errors:")
        for result in results:
            if result.error:
                print(
                    f"  student {result.student_number:02d} / {result.persona_id}: "
                    f"{result.error}"
                )
    return 0 if summary.error_count == 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
