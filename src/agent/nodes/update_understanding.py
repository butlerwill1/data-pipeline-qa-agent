from ..embed import embed
from ..llm import call_structured
from ..mongo import collections, now_utc, update_run_status
from ..state import State

SCHEMA = """{
  "table_id": "string",
  "business_description": "string",
  "grain": {
    "columns": ["string"],
    "confidence": "high|medium|low",
    "evidence": ["string"]
  },
  "freshness_expectation": {
    "cadence": "string",
    "expected_lag": "string",
    "confidence": "high|medium|low",
    "source": "string"
  },
  "important_columns": [
    {
      "name": "string",
      "role": "string",
      "nullable_expected": false,
      "confidence": "high|medium|low",
      "evidence": ["string"]
    }
  ],
  "known_risks": ["string"],
  "source_evidence": [
    {"type": "pipeline_code|user_answer|query_result|prior_understanding", "content": "string"}
  ]
}"""


def update_table_understanding(state: State) -> dict:
    update_run_status(state["run_id"], "running", current_node="update_table_understanding")

    cols = collections()
    extracted = state.get("extracted_logic") or {}
    profiles = state.get("table_profiles", {})
    business = state.get("user_business_context", [])
    prior = state.get("prior_context", {})

    understanding = dict(state.get("table_understanding", {}) or {})
    all_tables = list(state.get("source_tables", [])) + list(state.get("destination_tables", []))

    for table_id in all_tables:
        system = (
            "You synthesise a single, evidence-backed understanding of a data table from "
            "pipeline code, profiling queries, prior similar table understandings, and "
            "user-provided business context. Cite evidence for every claim. Mark "
            "confidence honestly. If a field is unknown, set it to a sensible empty "
            "value rather than fabricating."
        )
        user = (
            f"Table: {table_id}\n\n"
            f"Pipeline-extracted logic: {extracted}\n\n"
            f"This table's profile: {profiles.get(table_id, {})}\n\n"
            f"Prior similar understandings: {prior.get(table_id, [])}\n\n"
            f"User business context (Q&A): {business}\n\n"
            "Produce the table understanding."
        )

        parsing_failed = False
        parse_error: str | None = None
        try:
            doc = call_structured(system, user, SCHEMA, max_tokens=2048)
            if not isinstance(doc, dict) or not doc.get("business_description"):
                parsing_failed = True
                parse_error = "model returned an empty or non-dict structure"
                doc = {}
        except Exception as e:
            parsing_failed = True
            parse_error = str(e)
            doc = {}

        doc["table_id"] = table_id
        doc["run_id"] = state["run_id"]
        doc["updated_at"] = now_utc()
        doc["parsing_failed"] = parsing_failed
        if parsing_failed:
            doc["parse_error"] = parse_error

        if not parsing_failed:
            try:
                emb_text = f"{table_id}: {doc.get('business_description', '')}"
                doc["embedding"] = embed(emb_text)
            except Exception as e:
                doc["embedding_error"] = str(e)

        latest = cols["table_understandings"].find_one(
            {"table_id": table_id}, sort=[("version", -1)]
        )
        doc["version"] = (latest.get("version", 0) + 1) if latest else 1

        cols["table_understandings"].insert_one(dict(doc))
        understanding[table_id] = {k: v for k, v in doc.items() if k != "embedding"}

    return {"table_understanding": understanding}
