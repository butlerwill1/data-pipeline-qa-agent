from ..mongo import collections, now_utc, update_run_status
from ..state import State


def persist_run(state: State) -> dict:
    cols = collections()
    cols["pipeline_runs"].update_one(
        {"run_id": state["run_id"]},
        {
            "$set": {
                "status": "complete",
                "completed_at": now_utc(),
                "current_node": "persist_run",
            }
        },
    )
    update_run_status(state["run_id"], "complete", current_node="persist_run")
    return {}
