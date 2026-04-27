from __future__ import annotations

import importlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Optional


def ensure_legacy_root(legacy_root: Path) -> None:
    root = str(legacy_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)


def load_module(module_name: str, legacy_root: Path):
    ensure_legacy_root(legacy_root)
    return importlib.import_module(module_name)


def load_service_account_info(json_value: Optional[str], path_value: Optional[Path]) -> Optional[dict]:
    if json_value:
        return json.loads(json_value)
    if path_value and str(path_value) not in {"", "."} and path_value.exists() and path_value.is_file():
        return json.loads(path_value.read_text())
    return None


@contextmanager
def temporary_env(updates: Dict[str, Optional[str]]) -> Iterator[None]:
    original = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
