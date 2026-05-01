# Hash helpers for deterministic file fingerprints and cache key generation.
"""Utilities for deterministic hashing used by extraction cache lookups."""
from __future__ import annotations

import hashlib
import json


def sha256_text(content: str) -> str:
    """Return a SHA-256 hex digest for plain text input."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_cache_key(parts: dict[str, str | None]) -> str:
    """Build a stable cache key from structured identity parts."""
    packed = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return sha256_text(packed)
