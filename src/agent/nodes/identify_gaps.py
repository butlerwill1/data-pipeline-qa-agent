from ..llm import call_structured
from ..mongo import update_run_status
from ..state import State

SCHEMA = """{
  "gaps": [
    {
      "table_id": "string",
      "question": "string",
      "why_it_matters": "string"
    }
  ]
}"""


def identify_knowledge_gaps(state: State) -> dict:
    update_run_status(state["run_id"], "running", current_node="identify_knowledge_gaps")

    extracted = state.get("extracted_logic") or {}
    profiles = state.get("table_profiles", {})
    understanding = state.get("table_understanding", {})
    prior = state.get("prior_context", {})
    business = state.get("user_business_context", [])

    system = (
        "You are a data QA agent. Given what is currently known about a set of pipeline "
        "tables, identify the most important things that are NOT yet known and that "
        "would block writing accurate QA checks. Return at most 3 questions for the "
        "user, ranked by impact. If everything important is already known, return an "
        "empty list. Do not ask trivial or already-answered questions."
    )
    user = (
        f"Extracted pipeline logic: {extracted}\n\n"
        f"Table profiles: {profiles}\n\n"
        f"Current understanding: {understanding}\n\n"
        f"Prior context (similar tables seen before): {prior}\n\n"
        f"Business context already gathered: {business}\n\n"
        "What 0-3 most-important questions should we ask the user now?"
    )

    out = call_structured(system, user, SCHEMA, max_tokens=1024)
    gaps = out.get("gaps", []) if isinstance(out, dict) else []
    return {"knowledge_gaps": gaps}
