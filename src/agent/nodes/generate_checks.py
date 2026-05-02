from ..llm import call_structured
from ..mongo import update_run_status
from ..state import State

SCHEMA = """{
  "checks": [
    {
      "id": "string",
      "name": "string",
      "intent": "string",
      "target_table": "string",
      "sql": "string",
      "risk_level": "low|medium|high",
      "expected_outcome": "string",
      "category": "schema|freshness|row_count|null_check|duplicate_grain|reconciliation|aggregation_sanity|business_rule"
    }
  ]
}"""

EXEMPLAR_HINTS = """\
Reference QA SQL shapes the team has used before:
- nulls: SELECT COUNT(*) AS null_rows FROM "db"."t" WHERE col IS NULL
- freshness: SELECT MAX(ts_col) AS latest FROM "db"."t"
- row count by day: SELECT date_col, COUNT(*) c FROM "db"."t" GROUP BY 1 ORDER BY 1 DESC LIMIT 14
- duplicate grain: SELECT grain_a, grain_b, COUNT(*) c FROM "db"."t" GROUP BY 1,2 HAVING COUNT(*) > 1 LIMIT 10
- accepted values: SELECT col, COUNT(*) FROM "db"."t" GROUP BY 1 ORDER BY 2 DESC LIMIT 10
- reconciliation: SELECT date_col, COUNT(*) FROM "db"."source" GROUP BY 1 vs same on destination
"""


def generate_qa_checks(state: State) -> dict:
    update_run_status(state["run_id"], "running", current_node="generate_qa_checks")

    full_understanding = state.get("table_understanding", {}) or {}
    understanding = {
        tid: u for tid, u in full_understanding.items() if not u.get("parsing_failed")
    }
    if not understanding:
        return {"candidate_checks": []}
    prior = state.get("prior_context", {})
    profiles = state.get("table_profiles", {})

    schema_block_lines = ["Authoritative schemas (USE ONLY THESE COLUMNS — do not invent column names):"]
    for table_id, profile in profiles.items():
        meta = profile.get("metadata", {}) or {}
        cols = meta.get("columns", []) or []
        partitions = meta.get("partition_keys", []) or []
        schema_block_lines.append(
            f"- {table_id}: columns=[{', '.join(c['name'] for c in cols)}]"
            + (f", partitions=[{', '.join(p['name'] for p in partitions)}]" if partitions else "")
        )
    schema_block = "\n".join(schema_block_lines)

    system = (
        "You generate concrete SQL QA checks for data tables based on what is known "
        "about their grain, freshness expectation, important columns, and known risks. "
        "Output Athena/Presto-compatible SQL. Always quote database and table names. "
        "Always include a LIMIT on SELECTs. Prefer cheap metadata queries first. "
        "CRITICAL: every column you reference in SQL MUST appear in the authoritative "
        "schema list provided in the user message. Never invent or guess column names. "
        "If a check would require a column that does not exist, skip it."
    )
    user = (
        f"{schema_block}\n\n"
        f"{EXEMPLAR_HINTS}\n\n"
        f"Table understandings to QA: {understanding}\n\n"
        f"Prior similar checks: {prior}\n\n"
        "Generate 4-8 useful checks across the tables. Reference only the columns listed above."
    )

    out = call_structured(system, user, SCHEMA, max_tokens=3072)
    checks = out.get("checks", []) if isinstance(out, dict) else []
    return {"candidate_checks": checks}
