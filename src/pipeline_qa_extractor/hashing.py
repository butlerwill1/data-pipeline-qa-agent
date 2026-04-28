# Hash helpers for deterministic file fingerprints and cache key generation.
from __future__ import annotations

import hashlib
import json


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_cache_key(parts: dict[str, str | None]) -> str:
    packed = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return sha256_text(packed)
