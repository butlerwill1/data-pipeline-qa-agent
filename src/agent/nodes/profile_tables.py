"""Combine Glue metadata and lightweight Athena profiling queries.

This node is deliberately conservative. It gathers enough schema and freshness
signals to support later reasoning without running expensive exploratory SQL.
The result is stored only in the in-memory graph state, not as a dedicated
MongoDB collection.
"""

from ..athena import run as athena_run
from ..glue import get_table_metadata
from ..mongo import update_run_status
from ..state import State


def profile_tables(state: State) -> dict:
    """Profile each source and destination table referenced by the run.

    For each table, the node fetches Glue metadata and then runs a small set of
    safe Athena queries such as row counts and min/max timestamps.
    """
    update_run_status(state["run_id"], "running", current_node="profile_tables")

    profiles = dict(state.get("table_profiles", {}) or {})
    all_tables = list(state.get("source_tables", [])) + list(state.get("destination_tables", []))

    extracted = state.get("extracted_logic") or {}
    candidate_ts = extracted.get("candidate_timestamp_columns", []) or []

    for table_id in all_tables:
        if table_id in profiles:
            # Reuse any previously populated profile when resuming from a
            # checkpoint instead of repeating the same external calls.
            continue

        meta = get_table_metadata(table_id)
        profile: dict = {"metadata": meta, "queries": {}}

        if "error" in meta:
            # Preserve the metadata error in state so downstream reasoning can
            # explain why the table could not be profiled.
            profiles[table_id] = profile
            continue

        athena_table = meta.get("name", table_id.split(".")[-1])
        db = meta.get("database")
        col_names = [c["name"] for c in meta.get("columns", [])]

        rc = athena_run(
            f'SELECT COUNT(*) AS row_count FROM "{db}"."{athena_table}"',
            database=db,
        )
        profile["queries"]["row_count"] = rc

        for ts in candidate_ts:
            if ts in col_names:
                # Only probe timestamp bounds for columns already inferred from the pipeline.
                mm = athena_run(
                    f'SELECT MIN({ts}) AS min_ts, MAX({ts}) AS max_ts FROM "{db}"."{athena_table}"',
                    database=db,
                )
                profile["queries"][f"min_max_{ts}"] = mm
                break

        # Keep the full per-table profile in state so later nodes can cite both
        # schema metadata and observed query outputs.
        profiles[table_id] = profile

    return {"table_profiles": profiles}
