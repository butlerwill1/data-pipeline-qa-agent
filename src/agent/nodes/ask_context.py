"""Pause the graph and collect missing business context from a human.

This node is the handoff point between autonomous reasoning and
human-in-the-loop clarification. It persists the questions to MongoDB so the
web app or daemon can surface them, interrupts the graph, and then normalises
the answers back into ``user_business_context`` when execution resumes.
"""

import uuid

from langgraph.types import interrupt

from ..mongo import collections, now_utc, update_run_status
from ..state import State


def ask_business_context(state: State) -> dict:
    """Persist pending questions, interrupt the graph, and collect answers.

    The node returns only incremental state updates:
    - ``user_business_context`` enriched with resumed answers
    - ``iteration_count`` incremented to enforce the graph's retry limit
    """
    gaps = state.get("knowledge_gaps", []) or []
    if not gaps:
        # If the upstream node decided there is nothing left to ask, simply
        # advance the loop counter and let the graph continue.
        return {"iteration_count": (state.get("iteration_count") or 0) + 1}

    cols = collections()
    update_run_status(state["run_id"], "awaiting_user", current_node="ask_business_context")

    question_records = []
    for g in gaps:
        # Persist each question so web and daemon entrypoints can resume the same run.
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
    # The pending_questions collection is the durable handoff contract for any
    # UI or external process that needs to show the user what the agent is asking.
    cols["pending_questions"].insert_many([dict(r) for r in question_records])

    # LangGraph stores the interrupt payload in checkpoint state. Execution
    # stops here until a caller resumes the run with matching answers.
    answers = interrupt({"questions": question_records})

    bc = list(state.get("user_business_context", []) or [])
    if isinstance(answers, list):
        for a in answers:
            # Preserve the original question metadata beside each answer so later
            # reasoning nodes can cite exactly what the user clarified.
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
        # Support a single-answer resume payload for simpler callers and tests.
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
