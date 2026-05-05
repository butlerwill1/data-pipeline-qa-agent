"""Execute candidate QA SQL statements and persist the results.

This is the point where planned checks become real evidence. Each generated SQL
statement is run through the Athena helper, which applies read-only guardrails
and returns a compact result payload suitable for storage and reporting.
"""

import uuid

from ..athena import run as athena_run
from ..mongo import collections, now_utc, update_run_status
from ..state import State


def run_qa_queries(state: State) -> dict:
    """Run each generated QA check and store the execution record.

    The full executed-query list is both persisted to MongoDB and returned in
    state so later nodes can interpret and summarise the evidence immediately.
    """
    update_run_status(state["run_id"], "running", current_node="run_qa_queries")

    cols = collections()
    executed = list(state.get("executed_queries", []) or [])

    for check in state.get("candidate_checks", []) or []:
        # Athena.run handles SQL validation, timeout, and result normalisation.
        result = athena_run(check.get("sql", ""))
        record = {
            "run_id": state["run_id"],
            "query_id": check.get("id") or str(uuid.uuid4()),
            "check_name": check.get("name"),
            "purpose": check.get("intent"),
            "category": check.get("category"),
            "target_table": check.get("target_table"),
            "sql": result.get("sql", check.get("sql")),
            "status": result.get("status"),
            "runtime_ms": result.get("runtime_ms"),
            "row_count": result.get("row_count"),
            "result_sample": result.get("result_sample"),
            "error": result.get("error") or result.get("reason"),
            "executed_at": now_utc(),
        }
        # Persist a run-local execution log for UI inspection and historical review.
        cols["executed_queries"].insert_one(dict(record))
        executed.append(record)

    return {"executed_queries": executed}
