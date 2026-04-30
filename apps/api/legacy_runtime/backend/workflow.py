"""Workflow readiness helpers for lightweight cross-page checks.

This module only checks current scaffold prerequisites based on saved
session-state objects. It does not execute any product logic.
"""

from __future__ import annotations

from typing import Dict, List

from backend.storage import (
    has_audience_filter,
    has_business_product_context,
    has_experiment_plan,
    has_interview_transcripts,
    has_mock_response_records,
    has_research_brief,
    has_survey_schema,
)


# Stage prerequisites are intentionally minimal for the current scaffold phase.
STAGE_PREREQUISITES: Dict[str, List[str]] = {
    "audience": ["audience"],
    "experiment": ["experiment"],
    "survey_upload": ["audience", "experiment"],
    "run_simulation": ["audience", "experiment", "survey_schema"],
    "analysis": ["audience", "experiment", "survey_schema", "mock_response_records"],
    "insights": ["audience", "experiment", "survey_schema", "mock_response_records"],
    "interview_synthesis": ["audience", "business_product_context"],
    "interview_insights": ["interview_transcripts", "research_brief"],
}


def get_workflow_status() -> Dict[str, bool]:
    """Return current readiness state for core setup objects."""
    return {
        "audience": has_audience_filter(),
        "business_product_context": has_business_product_context(),
        "experiment": has_experiment_plan(),
        "survey_schema": has_survey_schema(),
        "mock_response_records": has_mock_response_records(),
        "interview_transcripts": has_interview_transcripts(),
        "research_brief": has_research_brief(),
    }


def missing_prerequisites_for(stage_name: str) -> List[str]:
    """Return missing prerequisite keys for the requested stage.

    Unknown stage names return an empty list to fail safely.
    """
    status = get_workflow_status()
    required = STAGE_PREREQUISITES.get(stage_name, [])
    return [step for step in required if not status.get(step, False)]


def is_ready_for(stage_name: str) -> bool:
    """Return True when all prerequisites for a stage are satisfied."""
    return len(missing_prerequisites_for(stage_name)) == 0
