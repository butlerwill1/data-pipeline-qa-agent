import uuid

from langgraph.types import interrupt

from ..mongo import collections, now_utc, update_run_status
from ..state import State


def ask_business_context(state: State) -> dict:
    gaps = state.get("knowledge_gaps", []) or []
    if not gaps:
        return {"iteration_count": (state.get("iteration_count") or 0) + 1}

    cols = collections()
    update_run_status(state["run_id"], "awaiting_user", current_node="ask_business_context")

    question_records = []
    for g in gaps:
        qid = str(uuid.uuid4())
        rec = {
            "run_id": state["run_id"],
            "question_id": qid,
            "table_id": g.get("table_id"),
            "question": g.get("question"),
            "why_it_matters": g.get("why_it_matters"),
            "created_at": now_utc(),
        }
        question_records.append(rec)
    cols["pending_questions"].insert_many([dict(r) for r in question_records])

    answers = interrupt({"questions": question_records})

    bc = list(state.get("user_business_context", []) or [])
    if isinstance(answers, list):
        for a in answers:
            bc.append(
                {
                    "run_id": state["run_id"],
                    "question_id": a.get("question_id"),
                    "table_id": a.get("table_id"),
                    "question": a.get("question"),
                    "answer": a.get("answer"),
                    "answered_at": now_utc(),
                }
            )
    elif isinstance(answers, dict):
        bc.append(
            {
                "run_id": state["run_id"],
                **answers,
                "answered_at": now_utc(),
            }
        )

    update_run_status(state["run_id"], "running", current_node="ask_business_context")
    return {
        "user_business_context": bc,
        "iteration_count": (state.get("iteration_count") or 0) + 1,
    }
