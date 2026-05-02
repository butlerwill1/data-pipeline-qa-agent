from ..embed import embed
from ..mongo import collections, update_run_status
from ..state import State


def retrieve_prior_understanding(state: State) -> dict:
    update_run_status(state["run_id"], "running", current_node="retrieve_prior_understanding")

    cols = collections()
    prior = dict(state.get("prior_context", {}) or {})

    all_tables = list(state.get("source_tables", [])) + list(state.get("destination_tables", []))

    for table_id in all_tables:
        if table_id in prior:
            continue
        try:
            query_vec = embed(f"data table named {table_id}")
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
            results = [{"warning": f"vector search unavailable: {e}"}]
        prior[table_id] = results

    return {"prior_context": prior}
