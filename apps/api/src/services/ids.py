from __future__ import annotations

from uuid import uuid4


def make_public_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"

