# File loading utilities with explicit size guardrails for prompt safety.
from __future__ import annotations

from pathlib import Path


class InputTooLargeError(ValueError):
    pass


def read_text_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def build_input_bundle(pipeline_file: str, dag_file: str | None, max_chars: int) -> tuple[str, str | None, int]:
    pipeline_text = read_text_file(pipeline_file)
    dag_text = read_text_file(dag_file) if dag_file else None

    total_chars = len(pipeline_text) + (len(dag_text) if dag_text else 0)
    if total_chars > max_chars:
        raise InputTooLargeError(
            f"Input too large: {total_chars} characters exceeds max of {max_chars}. "
            "Use smaller files or raise --max-input-chars."
        )

    return pipeline_text, dag_text, total_chars
