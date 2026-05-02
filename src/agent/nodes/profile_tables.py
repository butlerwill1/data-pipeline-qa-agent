from ..athena import run as athena_run
from ..glue import get_table_metadata
from ..mongo import update_run_status
from ..state import State


def profile_tables(state: State) -> dict:
    update_run_status(state["run_id"], "running", current_node="profile_tables")

    profiles = dict(state.get("table_profiles", {}) or {})
    all_tables = list(state.get("source_tables", [])) + list(state.get("destination_tables", []))

    extracted = state.get("extracted_logic") or {}
    candidate_ts = extracted.get("candidate_timestamp_columns", []) or []

    for table_id in all_tables:
        if table_id in profiles:
            continue

        meta = get_table_metadata(table_id)
        profile: dict = {"metadata": meta, "queries": {}}

        if "error" in meta:
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
                mm = athena_run(
                    f'SELECT MIN({ts}) AS min_ts, MAX({ts}) AS max_ts FROM "{db}"."{athena_table}"',
                    database=db,
                )
                profile["queries"][f"min_max_{ts}"] = mm
                break

        profiles[table_id] = profile

    return {"table_profiles": profiles}
