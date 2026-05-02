"""Mongo change-stream helpers used by the daemon.

The agent watches two collections:
- pipeline_runs (insert with status="pending") -> kicks off a new graph run
- user_answers (insert) -> resumes a paused run that was awaiting that answer
"""

from typing import Iterator

from .mongo import collections


def watch_pending_runs() -> Iterator[dict]:
    cols = collections()
    pipeline = [
        {
            "$match": {
                "operationType": {"$in": ["insert", "update", "replace"]},
                "fullDocument.status": "pending",
            }
        }
    ]
    try:
        with cols["pipeline_runs"].watch(
            pipeline, full_document="updateLookup"
        ) as stream:
            for change in stream:
                doc = change.get("fullDocument") or {}
                if doc.get("status") == "pending":
                    yield doc
    except Exception:
        # Fallback for non-replica-set environments: poll
        seen: set[str] = set()
        import time

        while True:
            for doc in cols["pipeline_runs"].find({"status": "pending"}):
                rid = doc.get("run_id")
                if rid and rid not in seen:
                    seen.add(rid)
                    yield doc
            time.sleep(1.0)


def watch_user_answers() -> Iterator[dict]:
    cols = collections()
    pipeline = [{"$match": {"operationType": "insert"}}]
    try:
        with cols["user_answers"].watch(
            pipeline, full_document="updateLookup"
        ) as stream:
            for change in stream:
                doc = change.get("fullDocument") or {}
                if doc:
                    yield doc
    except Exception:
        import time

        seen: set[str] = set()
        while True:
            for doc in cols["user_answers"].find():
                key = f"{doc.get('run_id')}:{doc.get('question_id')}"
                if key not in seen:
                    seen.add(key)
                    yield doc
            time.sleep(1.0)


def collect_answers_for_run(run_id: str) -> list[dict]:
    cols = collections()
    pending = list(cols["pending_questions"].find({"run_id": run_id}))
    qids = {q.get("question_id") for q in pending}
    answers = list(
        cols["user_answers"].find({"run_id": run_id, "question_id": {"$in": list(qids)}})
    )
    by_qid = {a.get("question_id"): a for a in answers}
    if len(by_qid) < len(qids):
        return []  # not all answered yet
    out = []
    for q in pending:
        a = by_qid.get(q.get("question_id"))
        if not a:
            continue
        out.append(
            {
                "question_id": q.get("question_id"),
                "table_id": q.get("table_id"),
                "question": q.get("question"),
                "answer": a.get("answer"),
            }
        )
    return out
