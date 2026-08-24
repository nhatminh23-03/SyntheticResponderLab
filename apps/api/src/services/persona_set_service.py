"""Fixed persona set: a reviewer-frozen selection of preview personas.

Data layout:
  - FixedPersonaSet       → at most one per study; pins a PersonaPreviewRun (the candidate batch)
  - FixedPersonaSetMember → the selected PersonaPreviewPersona rows, with reviewer notes

The set exists so later interview runs use the exact persisted persona records the reviewer
chose, even after newer previews repoint Study.latest_persona_preview_run_id.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.persistence.models import (
    FixedPersonaSet,
    FixedPersonaSetMember,
    PersonaPreviewPersona,
    PersonaPreviewRun,
    Study,
    utcnow,
)
from src.schemas.study import FixedPersonaSetResult, PersonaSetSelection
from src.services.exceptions import ConflictApiError, NotFoundApiError, ValidationApiError
from src.services.ids import make_public_id

REQUIRED_SELECTION_COUNT = 5


def get_persona_set(session: Session, study: Study) -> Dict[str, Any]:
    persona_set = _get_set(session, study)
    return {"persona_set": _serialize_persona_set(persona_set) if persona_set else None}


def upsert_persona_set_draft(
    session: Session,
    study: Study,
    *,
    preview_run_id: str,
    selections: List[PersonaSetSelection],
) -> Dict[str, Any]:
    persona_set = _get_set(session, study)
    if persona_set is not None and persona_set.status == "finalized":
        raise ConflictApiError("The fixed persona set is finalized and can no longer be edited.")

    preview_run = session.scalars(
        select(PersonaPreviewRun).where(
            PersonaPreviewRun.public_id == preview_run_id,
            PersonaPreviewRun.study_id == study.id,
        )
    ).first()
    if preview_run is None:
        raise NotFoundApiError("Persona preview run not found for this study.")

    candidates_by_id = {str(persona.id): persona for persona in preview_run.personas}
    seen: set = set()
    members: List[FixedPersonaSetMember] = []
    for position, selection in enumerate(selections):
        candidate_id = selection.candidate_id
        if candidate_id in seen:
            raise ValidationApiError(f"Duplicate candidate_id in selection: {candidate_id}")
        seen.add(candidate_id)
        persona = candidates_by_id.get(candidate_id)
        if persona is None:
            raise ValidationApiError(
                f"candidate_id {candidate_id} does not belong to preview run {preview_run_id}."
            )
        members.append(
            FixedPersonaSetMember(
                preview_persona_id=persona.id,
                position=position,
                reviewer_note=selection.reviewer_note,
            )
        )

    if persona_set is None:
        persona_set = FixedPersonaSet(
            public_id=make_public_id("fps"),
            study_id=study.id,
            preview_run_id=preview_run.id,
            status="draft",
        )
        session.add(persona_set)
    else:
        # Delete the old members before inserting replacements — the unit of work would
        # otherwise INSERT first and trip UNIQUE(set_id, preview_persona_id) on overlap.
        persona_set.members.clear()
        session.flush()

    persona_set.preview_run_id = preview_run.id
    persona_set.generation_mode = preview_run.generation_mode
    persona_set.members.extend(members)
    persona_set.updated_at = utcnow()
    session.commit()
    session.refresh(persona_set)
    return {"persona_set": _serialize_persona_set(persona_set)}


def finalize_persona_set(session: Session, study: Study) -> Dict[str, Any]:
    persona_set = _get_set(session, study)
    if persona_set is None:
        raise ConflictApiError("No persona set draft exists. Save a selection before finalizing.")
    if persona_set.status == "finalized":
        raise ConflictApiError("The fixed persona set is already finalized.")
    if len(persona_set.members) != REQUIRED_SELECTION_COUNT:
        raise ConflictApiError(
            f"Exactly {REQUIRED_SELECTION_COUNT} personas must be selected to finalize "
            f"(currently {len(persona_set.members)})."
        )

    persona_set.status = "finalized"
    persona_set.finalized_at = utcnow()
    persona_set.updated_at = utcnow()
    session.commit()
    session.refresh(persona_set)
    return {"persona_set": _serialize_persona_set(persona_set)}


def resolve_interview_personas(
    session: Session, study: Study
) -> Tuple[Optional[FixedPersonaSet], Optional[PersonaPreviewRun], List[Dict[str, Any]]]:
    """The persona source for an interview run.

    A finalized fixed set wins and yields exactly its members; otherwise the latest preview
    run is used in full — byte-identical to the pre-fixed-set behavior.
    """
    persona_set = _get_set(session, study)
    if persona_set is not None and persona_set.status == "finalized":
        members = sorted(persona_set.members, key=lambda m: m.preview_persona.row_index)
        personas = [member.preview_persona.persona_json for member in members]
        return persona_set, persona_set.preview_run, personas

    if not study.latest_persona_preview_run_id:
        return None, None, []
    latest = session.get(PersonaPreviewRun, study.latest_persona_preview_run_id)
    if latest is None:
        return None, None, []
    personas = [p.persona_json for p in sorted(latest.personas, key=lambda x: x.row_index)]
    return None, latest, personas


def _get_set(session: Session, study: Study) -> Optional[FixedPersonaSet]:
    return session.scalars(
        select(FixedPersonaSet).where(FixedPersonaSet.study_id == study.id)
    ).first()


def _serialize_persona_set(persona_set: FixedPersonaSet) -> Dict[str, Any]:
    run = persona_set.preview_run
    candidate_rows = sorted(run.personas, key=lambda p: p.row_index)
    candidates = [
        {**persona.persona_json, "candidate_id": str(persona.id), "row_index": persona.row_index}
        for persona in candidate_rows
    ]
    selections = [
        {
            "candidate_id": str(member.preview_persona_id),
            "persona_id": member.preview_persona.persona_id,
            "reviewer_note": member.reviewer_note,
        }
        for member in sorted(persona_set.members, key=lambda m: m.position)
    ]
    return FixedPersonaSetResult(
        set_id=persona_set.public_id,
        status=persona_set.status,
        preview_run_id=run.public_id,
        generation_mode=persona_set.generation_mode,
        grounded_priors_available=run.grounded_priors_available,
        seed=run.seed,
        candidate_count=len(candidates),
        generated_at=run.created_at,
        selections=selections,
        candidates=candidates,
        created_at=persona_set.created_at,
        updated_at=persona_set.updated_at,
        finalized_at=persona_set.finalized_at,
    ).model_dump(mode="json")
