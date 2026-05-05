"""Convert executed query results into human-readable findings.

At this stage the agent has concrete query outputs. This node asks the model to
turn those outputs into concise pass/warn/fail findings with evidence and
recommended actions, then persists those findings for later reporting and UI
display.
"""

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
    """Interpret executed QA checks and persist any resulting findings.

    Findings are stored individually in MongoDB and also returned in the graph
    state so the report-writing node can consume them immediately.
    """
    update_run_status(state["run_id"], "running", current_node="interpret_results")

    cols = collections()
    full_understanding = state.get("table_understanding", {}) or {}
    understanding = {
        tid: u for tid, u in full_understanding.items() if not u.get("parsing_failed")
    }
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
        # Add run-local metadata so each finding can be queried independently
        # from the final report document.
        f["run_id"] = state["run_id"]
        f["created_at"] = now_utc()
        try:
            cols["findings"].insert_one(dict(f))
        except Exception:
            # Duplicate or persistence failures should not stop the report step;
            # the in-memory state still carries the finding forward.
            pass

    return {"findings": findings}
