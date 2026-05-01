# Prompt builders for shared extraction instructions and technology-specific output blocks.
"""Prompt construction utilities for extraction and one-shot JSON repair."""
from __future__ import annotations

from pipeline_qa_extractor.models import Technology
from pipeline_qa_extractor.technology_templates import get_technology_detail_template

PROMPT_VERSION = "v1"

GENERIC_SCHEMA = """
"generic_extraction": {
  "pipeline_name": "... or null",
  "source_tables": [
    {
      "name": "catalog.schema.table or schema.table or table",
      "evidence_snippet": "exact short snippet from code",
      "how_detected": "spark.table | read.table | SQL FROM | INSERT source | psycopg query | unknown",
      "confidence": "high | medium | low"
    }
  ],
  "destination_tables": [
    {
      "name": "...",
      "evidence_snippet": "...",
      "how_detected": "saveAsTable | INSERT INTO | CREATE TABLE AS | COPY | dbt model | unknown",
      "confidence": "high | medium | low"
    }
  ],
  "referenced_columns": [
    {
      "name": "...",
      "table_if_known": "... or null",
      "context": "selected | joined | filtered | grouped | aggregated | written | partitioned | ordered | unknown",
      "evidence_snippet": "...",
      "confidence": "high | medium | low"
    }
  ],
  "read_operations": [
    {
      "operation_type": "table_read | sql_query | file_read | unknown",
      "target": "table name, file path, or query description",
      "evidence_snippet": "...",
      "confidence": "high | medium | low"
    }
  ],
  "write_operations": [
    {
      "operation_type": "table_write | insert | merge | update | create_table_as | file_write | unknown",
      "target": "...",
      "write_disposition": "append | overwrite | merge | update | create_or_replace | unknown | null",
      "evidence_snippet": "...",
      "confidence": "high | medium | low"
    }
  ],
  "unknowns": [],
  "warnings": []
}
""".strip()


def build_system_prompt(technology: Technology) -> str:
    """Build the shared system prompt plus the selected technology detail schema."""
    details_schema = get_technology_detail_template(technology)
    inactive_block = '"postgres": null' if technology == "databricks" else '"databricks": null'

    return f"""
You are extracting structural pipeline metadata from Python code.
Return strict JSON only, no markdown.

Rules:
- Separate structural facts, unknowns, and warnings.
- Do not create QA checks.
- Do not infer business intent unless directly explicit in code/comments.
- Every important object must include evidence_snippet copied from input.
- If unsure, set confidence low and add an unknown.
- Only populate the selected technology block.
- Set non-selected technology block to null.

Return shape:
{{
  {GENERIC_SCHEMA},
  "technology_details": {{
    {details_schema},
    {inactive_block}
  }}
}}
""".strip()


def build_user_prompt(pipeline_file: str, pipeline_code: str, dag_file: str | None, dag_code: str | None) -> str:
    """Build a bounded user prompt containing pipeline code and optional DAG code."""
    dag_section = ""
    if dag_file and dag_code is not None:
        dag_section = (
            f"\n\nOptional DAG/Scheduler file: {dag_file}\n"
            "```python\n"
            f"{dag_code}\n"
            "```"
        )

    return (
        f"Pipeline file: {pipeline_file}\n"
        "```python\n"
        f"{pipeline_code}\n"
        "```"
        f"{dag_section}\n\n"
        "Extract JSON now."
    )


def build_repair_prompt(validation_error: str, invalid_json_text: str) -> str:
    """Build a strict repair instruction that asks the model for JSON only."""
    return (
        "Repair the JSON to satisfy validation errors. Return JSON only, no markdown.\n\n"
        f"Validation error:\n{validation_error}\n\n"
        f"Invalid JSON text:\n{invalid_json_text}"
    )
