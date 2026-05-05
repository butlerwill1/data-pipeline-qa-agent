"""Terminal node that marks a QA run as complete in MongoDB.

The substantive artefacts are already stored by earlier nodes. This final step
only flips the run lifecycle record into its terminal ``complete`` state.
"""

from ..mongo import collections, now_utc, update_run_status
from ..state import State


def persist_run(state: State) -> dict:
    """Persist final completion state for a finished run.

    Returns an empty dict because this is the terminal node and no downstream
    node consumes additional state updates.
    """
    cols = collections()
    # Update the lifecycle document directly so completion timestamps are easy
    # to query without reading the final report collection.
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
    # Keep the generic status helper in sync so shared fields like updated_at
    # are refreshed consistently with the rest of the application.
    update_run_status(state["run_id"], "complete", current_node="persist_run")
    return {}
