from ..llm import call_structured
from ..mongo import collections, now_utc, update_run_status
from ..state import State

SCHEMA = """{
  "findings": [
    {
      "title": "string",
      "severity": "pass|warn|fail",
      "evidence": "string",
      "recommended_action": "string",
      "related_check": "string",
      "related_table": "string"
    }
  ]
}"""


def interpret_results(state: State) -> dict:
    update_run_status(state["run_id"], "running", current_node="interpret_results")

    cols = collections()
    understanding = state.get("table_understanding", {})
    executed = state.get("executed_queries", [])

    system = (
        "You interpret the results of QA queries against a known understanding of the "
        "tables. For each meaningful result, produce a finding with severity (pass, "
        "warn, fail), explicit evidence quoting the result values, and a recommended "
        "action. Be concise but precise."
    )
    user = (
        f"Table understandings: {understanding}\n\n"
        f"Executed queries with results: {executed}\n\n"
        "Produce findings."
    )

    out = call_structured(system, user, SCHEMA, max_tokens=2048)
    findings = out.get("findings", []) if isinstance(out, dict) else []

    for f in findings:
        f["run_id"] = state["run_id"]
        f["created_at"] = now_utc()
        try:
            cols["findings"].insert_one(dict(f))
        except Exception:
            pass

    return {"findings": findings}
