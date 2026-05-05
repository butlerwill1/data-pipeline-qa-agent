"""Retrieve similar historical table understandings via vector search.

The agent uses prior versions of stored table memory as weak guidance for the
current run. This node embeds each table identifier and queries Atlas Vector
Search against previously persisted ``table_understandings`` documents.
"""

from ..embed import embed
from ..mongo import collections, update_run_status
from ..state import State


def retrieve_prior_understanding(state: State) -> dict:
    """Look up similar table-understanding documents for each referenced table.

    The returned ``prior_context`` is advisory only. Later nodes still ground
    their reasoning in the current pipeline code and current table profile.
    """
    update_run_status(state["run_id"], "running", current_node="retrieve_prior_understanding")

    cols = collections()
    prior = dict(state.get("prior_context", {}) or {})

    all_tables = list(state.get("source_tables", [])) + list(state.get("destination_tables", []))

    for table_id in all_tables:
        if table_id in prior:
            # Resume paths may already have prior context from an earlier pass.
            continue
        try:
            query_vec = embed(f"data table named {table_id}")
            # Strip the stored embedding from results because downstream prompts
            # only need the semantic content of the prior documents.
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "table_understandings_vec",
                        "path": "embedding",
                        "queryVector": query_vec,
                        "numCandidates": 30,
                        "limit": 3,
                    }
                },
                {"$project": {"embedding": 0, "_id": 0}},
            ]
            results = list(cols["table_understandings"].aggregate(pipeline))
        except Exception as e:
            # Vector search is helpful but non-critical; keep the run moving even
            # when the index or embedding service is unavailable.
            results = [{"warning": f"vector search unavailable: {e}"}]
        prior[table_id] = results

    return {"prior_context": prior}
