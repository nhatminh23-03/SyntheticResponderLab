from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class WorkflowStage(BaseModel):
    stage_key: str
    status: str
    hard_blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    completed_at: Optional[datetime] = None


class WorkflowReadiness(BaseModel):
    stages: List[WorkflowStage]
    ready_for_persona_preview: bool
    next_recommended_stage: Optional[str] = None
