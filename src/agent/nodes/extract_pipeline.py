from ..llm import call_structured
from ..mongo import update_run_status
from ..state import State

SCHEMA = """{
  "confirmed_source_tables": [{"id": "string", "evidence": "string"}],
  "confirmed_destination_tables": [{"id": "string", "evidence": "string"}],
  "transformations": ["string"],
  "filters": ["string"],
  "joins": ["string"],
  "aggregations": ["string"],
  "candidate_grain_columns": ["string"],
  "candidate_timestamp_columns": ["string"],
  "business_logic_observations": ["string"]
}"""


def extract_pipeline_logic(state: State) -> dict:
    update_run_status(state["run_id"], "running", current_node="extract_pipeline_logic")

    code = state.get("pipeline_code", "") or ""
    if len(code) > 30000:
        code = code[:15000] + "\n\n... (middle elided for length) ...\n\n" + code[-15000:]

    system = (
        "You are a senior data engineer analysing a pipeline file to extract its data "
        "flow. Be precise. Ground every observation in the source code."
    )
    user = (
        f"Source tables (claimed by the operator): {state.get('source_tables', [])}\n"
        f"Destination tables (claimed by the operator): {state.get('destination_tables', [])}\n\n"
        "Pipeline code:\n```\n"
        f"{code}\n"
        "```\n\n"
        "Extract the pipeline's data flow."
    )

    extracted = call_structured(system, user, SCHEMA, max_tokens=2048)
    return {"extracted_logic": extracted}
