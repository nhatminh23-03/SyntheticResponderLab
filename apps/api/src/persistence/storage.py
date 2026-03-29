from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Tuple

from src.config.settings import AppSettings


def sanitize_filename(filename: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (filename or "").strip())
    return cleaned or fallback


def asset_subdir(asset_type: str) -> str:
    mapping = {
        "survey_upload": "survey",
        "product_image": "product-images",
        "scraped_page_text": "scraped-page-text",
    }
    return mapping.get(asset_type, asset_type)


def compute_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def persist_asset_bytes(
    settings: AppSettings,
    *,
    study_public_id: str,
    asset_public_id: str,
    asset_type: str,
    filename: str,
    payload: bytes,
) -> Tuple[str, int, str]:
    relative_key = (
        Path("studies")
        / study_public_id
        / asset_subdir(asset_type)
        / asset_public_id
        / "original"
        / sanitize_filename(filename, "payload.bin")
    )
    absolute_path = settings.artifacts_root / relative_key
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(payload)
    return str(relative_key), len(payload), compute_sha256(payload)
