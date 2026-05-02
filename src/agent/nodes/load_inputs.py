import uuid

from ..mongo import collections, now_utc
from ..state import State


def load_inputs(state: State) -> dict:
    run_id = state.get("run_id") or str(uuid.uuid4())
    cols = collections()

    cols["pipeline_runs"].update_one(
        {"run_id": run_id},
        {
            "$set": {
                "run_id": run_id,
                "pipeline_path": state.get("pipeline_path"),
                "source_tables": state.get("source_tables", []),
                "destination_tables": state.get("destination_tables", []),
                "status": "running",
                "started_at": now_utc(),
                "current_node": "load_inputs",
            }
        },
        upsert=True,
    )

    return {
        "run_id": run_id,
        "iteration_count": state.get("iteration_count") or 0,
        "table_profiles": state.get("table_profiles") or {},
        "prior_context": state.get("prior_context") or {},
        "table_understanding": state.get("table_understanding") or {},
        "knowledge_gaps": state.get("knowledge_gaps") or [],
        "user_business_context": state.get("user_business_context") or [],
        "candidate_checks": state.get("candidate_checks") or [],
        "executed_queries": state.get("executed_queries") or [],
        "findings": state.get("findings") or [],
    }
