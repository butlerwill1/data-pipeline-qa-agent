"""Normalise the initial graph state and mark the run as started.

This node establishes the baseline state shape expected by the rest of the
graph. It also ensures a ``pipeline_runs`` document exists so external systems
can observe that the run has started even before later artefacts are generated.
"""

import uuid

from ..mongo import collections, now_utc
from ..state import State


def load_inputs(state: State) -> dict:
    """Initialise persisted run metadata and fill missing state collections.

    The return value is a clean baseline state with all list/dict fields present
    so later nodes do not need to repeat defensive default handling.
    """
    run_id = state.get("run_id") or str(uuid.uuid4())
    cols = collections()

    # Persist the initial run envelope as early as possible so the CLI, daemon,
    # and web UI all have a common run record to inspect.
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

    # LangGraph merges this partial dict into the checkpointed state. Any fields
    # omitted here remain absent until a later node writes them.
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
