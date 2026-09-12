from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.persistence.models import Persona


def list_personas(session: Session) -> List[dict]:
    personas = session.scalars(select(Persona).order_by(Persona.row_index)).all()
    return [dict(persona.profile_json) for persona in personas]
