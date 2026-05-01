# Technology-specific schema snippets injected into the shared extraction prompt.
"""Technology-specific JSON schema fragments for prompt composition."""
from __future__ import annotations

from pipeline_qa_extractor.models import Technology

DATABRICKS_DETAILS_SCHEMA = """
"databricks": {
  "spark_reads": [
    {
      "method": "spark.table | spark.sql | read.table | read.format | unknown",
      "target": "...",
      "evidence_snippet": "...",
      "confidence": "high | medium | low"
    }
  ],
  "spark_writes": [
    {
      "method": "saveAsTable | insertInto | sql_insert | merge | unknown",
      "target_table": "...",
      "mode": "append | overwrite | ignore | errorifexists | unknown | null",
      "format": "delta | parquet | unknown | null",
      "partition_columns": [],
      "replace_where": "... or null",
      "merge_condition": "... or null",
      "evidence_snippet": "...",
      "confidence": "high | medium | low"
    }
  ],
  "databricks_specific_features": [
    {
      "feature": "delta_table | describe_history_candidate | partitionBy | replaceWhere | merge_into | optimize | vacuum | unknown",
      "evidence_snippet": "...",
      "confidence": "high | medium | low"
    }
  ]
}
""".strip()

POSTGRES_DETAILS_SCHEMA = """
"postgres": {
  "sql_reads": [
    {
      "method": "SELECT | CTE | view_read | unknown",
      "target": "...",
      "evidence_snippet": "...",
      "confidence": "high | medium | low"
    }
  ],
  "sql_writes": [
    {
      "method": "INSERT INTO | UPDATE | DELETE | MERGE | CREATE TABLE AS | CREATE MATERIALIZED VIEW | COPY | unknown",
      "target_table": "...",
      "conflict_handling": "ON CONFLICT DO NOTHING | ON CONFLICT DO UPDATE | none | unknown | null",
      "returning_columns": [],
      "transaction_usage": "explicit_transaction | implicit | unknown | null",
      "evidence_snippet": "...",
      "confidence": "high | medium | low"
    }
  ],
  "postgres_specific_features": [
    {
      "feature": "on_conflict | returning | cte | materialized_view | copy | temp_table | transaction | index_reference | unknown",
      "evidence_snippet": "...",
      "confidence": "high | medium | low"
    }
  ]
}
""".strip()


def get_technology_detail_template(technology: Technology) -> str:
    """Return the detail-schema fragment that matches the selected technology."""
    if technology == "databricks":
        return DATABRICKS_DETAILS_SCHEMA
    return POSTGRES_DETAILS_SCHEMA
