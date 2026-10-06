"""The preloaded survey-run demo: answers saved from a synthetic run, served with no provider call."""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.services.exceptions import ConflictApiError

FIXTURE_PATH = Path(__file__).with_name("demo_survey_fixture.json.gz")
DEMO_WARNING = ("Preloaded demo: answers saved from a run on 2026-10-03 (four models, answers drawn from their stated odds). "
                "No AI was called.")
NOT_COVERED_MESSAGE = "The preloaded demo covers the Tahoe Mini survey; use a live run for this survey."
REASONS = {
    "requested": "You chose the preloaded demo.",
    "no_key": "No AI key is configured on this server, so the preloaded demo was shown instead of a live run.",
    "jev_unavailable": ("Jev is temporarily unavailable, so these are the PRELOADED DEMO answers from 2026-10-03, "
                        "not a live run. Retry to get live answers."),
}


@lru_cache(maxsize=1)
def load_fixture(path: str = str(FIXTURE_PATH)) -> Dict[str, Any]:
    return json.loads(gzip.decompress(Path(path).read_bytes()))


def build_demo_run_result(*, survey_payload: Dict[str, Any], experiment_payload: Dict[str, Any], reason: str,
                          detail: Optional[str] = None, fixture: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    fixture = fixture if fixture is not None else load_fixture()
    available = {qid.upper(): qid for qid in fixture["question_ids"]}
    questions: List[Dict[str, Any]] = list(survey_payload.get("questions") or [])
    covered = [q for q in questions if str(q.get("id", "")).upper() in available]
    if not covered:
        raise ConflictApiError(NOT_COVERED_MESSAGE)
    missing = [q["id"] for q in questions if str(q.get("id", "")).upper() not in available]
    sample = max(1, min(int(experiment_payload.get("sample_size") or len(fixture["respondents"])), len(fixture["respondents"])))
    respondents = fixture["respondents"][:sample]
    run_id = f"DEMO_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    survey_title = survey_payload.get("survey_title")
    records: List[Dict[str, Any]] = []
    for respondent in respondents:
        for question in covered:
            answer = respondent["answers"].get(available[str(question["id"]).upper()])
            if answer is None:
                continue
            records.append({"respondent_id": respondent["respondent_id"], "model": respondent["model"], "experiment_mode": "split",
                            "survey_title": survey_title, "question_id": question["id"], "question_text": question.get("text") or "",
                            "question_type": question.get("question_type") or "", "answer": answer, "segment_label": None,
                            "run_id": run_id, "is_fallback": False})
    warnings = [DEMO_WARNING, REASONS.get(reason, REASONS["requested"])]
    if detail:
        warnings.append(f"Detail: {detail}")
    if missing:
        warnings.append(f"Run live to answer these: {', '.join(missing)}")
    models_used = sorted({r["model"] for r in respondents})
    return {
        "run_id": run_id, "status": "completed",
        "run_counts": {"personas": len(respondents), "executions": len(respondents), "questions": len(questions), "answer_records": len(records)},
        "total_requested_responses": len(respondents), "total_generated_responses": len(respondents),
        "models_used": models_used, "experiment_mode": "split", "survey_title": survey_title, "question_count": len(questions),
        "notes": f"Preloaded demo from {fixture['source'].get('run_label')}.", "created_at": datetime.now(timezone.utc).isoformat(),
        "generation_mode": "demo_preloaded", "provider_model_name": None, "persona_generation_mode": "preloaded_s1",
        "grounded_priors_available": False, "cex_affordability_available": False, "geography_context": None, "prior_notes": [],
        "warnings": warnings,
        "generation_debug": {"generation_mode": "demo_preloaded", "executions": len(respondents), "answer_records": len(records),
                             "questions_total": len(records), "request_errors": 0, "provider_error_count": 0,
                             "malformed_json_count": 0, "questions_fallback_to_mock": 0, "questions_parsed_from_live": 0},
        "run_debug_summary": {},
        "run_conditions": {"context_influence": {"enabled": False, "sources": []}, "generation_mode": "demo_preloaded",
                           "selected_models": models_used},
        "personas": [r["persona"] for r in respondents],
        "response_records": records, "response_record_preview": records[:24],
        "survey_parse_warnings": list(survey_payload.get("parse_warnings", [])),
        "demo": {"reason": reason, "source": fixture["source"]},
    }
