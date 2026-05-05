"""Extract pipeline structure and business logic from source code.

This node is the first LLM-heavy reasoning step. It takes the raw pipeline
source plus any operator-supplied source and destination tables, then asks the
model to produce a structured summary of the pipeline's flow and candidate
grains/timestamps for downstream profiling.
"""

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
    """Summarise the pipeline's data flow from the provided source code.

    Returns:
        A partial state update containing ``extracted_logic``.
    """
    update_run_status(state["run_id"], "running", current_node="extract_pipeline_logic")

    code = state.get("pipeline_code", "") or ""
    if len(code) > 30000:
        # Keep prompts bounded while still retaining the start and end of large files.
        code = code[:15000] + "\n\n... (middle elided for length) ...\n\n" + code[-15000:]

    # The system prompt sets the model's role and operating rules. It tells the
    # model to behave like a careful senior data engineer and to stay grounded
    # in the pipeline source rather than inventing behaviour.
    system = (
        "You are a senior data engineer analysing a pipeline file to extract its data "
        "flow. Be precise. Ground every observation in the source code."
    )
    # The user prompt carries the task-specific payload for this run: the tables
    # the operator believes are involved plus the actual pipeline code to inspect.
    # In chat-model terms, this is the concrete request and evidence, while the
    # system prompt above defines how the model should approach that request.
    user = (
        f"Source tables (claimed by the operator): {state.get('source_tables', [])}\n"
        f"Destination tables (claimed by the operator): {state.get('destination_tables', [])}\n\n"
        "Pipeline code:\n```\n"
        f"{code}\n"
        "```\n\n"
        "Extract the pipeline's data flow."
    )

    # Downstream nodes treat this structure as the first pass of "what the
    # pipeline appears to do", so keeping the response typed matters.
    extracted = call_structured(system, user, SCHEMA, max_tokens=2048)
    return {"extracted_logic": extracted}
