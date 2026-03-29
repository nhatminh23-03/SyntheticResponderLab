from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from src.persistence.models import PersonaPreviewRun, Study, StudySectionState
from src.schemas.workflow import WorkflowReadiness, WorkflowStage


STAGE_ORDER = ["study_mode", "audience", "product", "market", "survey", "experiment"]


def _saved_at(section: Optional[StudySectionState]) -> Optional[datetime]:
    return section.saved_at if section and section.status == "saved" else None


def build_workflow(
    *,
    study: Study,
    sections: Dict[str, StudySectionState],
    latest_preview: Optional[PersonaPreviewRun],
) -> WorkflowReadiness:
    stages: List[WorkflowStage] = []

    for key in STAGE_ORDER:
        if key == "experiment":
            hard_blockers = [
                f"{required_key} not saved"
                for required_key in STAGE_ORDER[:-1]
                if sections[required_key].status != "saved"
            ]
            stage_status = "complete" if sections[key].status == "saved" else ("blocked" if hard_blockers else "ready")
            warnings = []
            if latest_preview and latest_preview.status == "completed":
                warnings.append("persona preview already generated for this study")
            stages.append(
                WorkflowStage(
                    stage_key=key,
                    status=stage_status,
                    hard_blockers=hard_blockers,
                    warnings=warnings,
                    completed_at=_saved_at(sections[key]),
                )
            )
            continue

        section = sections[key]
        stage_status = "complete" if section.status == "saved" else "blocked"
        hard_blockers = [] if section.status == "saved" else [f"{key} not saved"]
        stages.append(
            WorkflowStage(
                stage_key=key,
                status=stage_status,
                hard_blockers=hard_blockers,
                warnings=[],
                completed_at=_saved_at(section),
            )
        )

    ready_for_persona_preview = all(
        sections[key].status == "saved" for key in STAGE_ORDER
    )
    next_stage = next((stage.stage_key for stage in stages if stage.status != "complete"), None)
    return WorkflowReadiness(
        stages=stages,
        ready_for_persona_preview=ready_for_persona_preview,
        next_recommended_stage=next_stage,
    )
