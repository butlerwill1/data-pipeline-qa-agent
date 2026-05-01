# Tests for deterministic cache key generation from extraction identity fields.
"""Unit tests for cache key stability and key differentiation behavior."""
from pipeline_qa_extractor.hashing import build_cache_key


def test_cache_key_is_deterministic_for_same_parts() -> None:
    """The same logical identity should always produce the same cache key."""
    parts = {
        "pipeline_file_hash": "abc",
        "dag_file_hash": "def",
        "technology": "databricks",
        "model": "openai/gpt-4.1-mini",
        "prompt_version": "v1",
    }

    first = build_cache_key(parts)
    second = build_cache_key(dict(reversed(list(parts.items()))))

    assert first == second


def test_cache_key_changes_when_model_changes() -> None:
    """Changing one identity field must produce a different cache key."""
    parts = {
        "pipeline_file_hash": "abc",
        "dag_file_hash": None,
        "technology": "postgres",
        "model": "openai/gpt-4.1-mini",
        "prompt_version": "v1",
    }

    first = build_cache_key(parts)
    parts["model"] = "openai/gpt-4.1"
    second = build_cache_key(parts)

    assert first != second
