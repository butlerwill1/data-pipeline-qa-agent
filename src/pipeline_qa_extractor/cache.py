# Local JSON cache for extraction outputs and OpenRouter model metadata snapshots.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CACHE_DIR = Path(".pipeline_qa_cache")
EXTRACTIONS_DIR = CACHE_DIR / "extractions"
MODELS_CACHE_FILE = CACHE_DIR / "openrouter_models.json"


def ensure_cache_dirs() -> None:
    EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)


def extraction_cache_path(cache_key: str) -> Path:
    ensure_cache_dirs()
    return EXTRACTIONS_DIR / f"{cache_key}.json"


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_cached_extraction(cache_key: str) -> dict[str, Any] | None:
    return read_json(extraction_cache_path(cache_key))


def save_cached_extraction(cache_key: str, payload: dict[str, Any]) -> Path:
    path = extraction_cache_path(cache_key)
    write_json(path, payload)
    return path


def load_models_cache() -> dict[str, Any] | None:
    return read_json(MODELS_CACHE_FILE)


def save_models_cache(payload: dict[str, Any]) -> Path:
    write_json(MODELS_CACHE_FILE, payload)
    return MODELS_CACHE_FILE
