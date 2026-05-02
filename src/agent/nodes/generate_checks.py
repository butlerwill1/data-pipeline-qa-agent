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

    understanding = state.get("table_understanding", {})
    prior = state.get("prior_context", {})

    system = (
        "You generate concrete SQL QA checks for data tables based on what is known "
        "about their grain, freshness expectation, important columns, and known risks. "
        "Output Athena/Presto-compatible SQL. Always quote database and table names. "
        "Always include a LIMIT on SELECTs. Prefer cheap metadata queries first."
    )
    user = (
        f"{EXEMPLAR_HINTS}\n\n"
        f"Table understandings to QA: {understanding}\n\n"
        f"Prior similar checks: {prior}\n\n"
        "Generate 4-8 useful checks across the tables."
    )

    out = call_structured(system, user, SCHEMA, max_tokens=3072)
    checks = out.get("checks", []) if isinstance(out, dict) else []
    return {"candidate_checks": checks}
