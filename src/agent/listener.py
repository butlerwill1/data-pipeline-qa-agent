"""Mongo change-stream helpers used by the daemon.

The agent watches two collections:
- pipeline_runs (insert with status="pending") -> kicks off a new graph run
- user_answers (insert) -> resumes a paused run that was awaiting that answer

Each function in this module is a generator. Instead of returning one value and
finishing, it keeps yielding MongoDB documents over time as new events arrive.
That makes it a natural fit for the long-running loops in ``daemon.py``.
"""

from typing import Iterator

from .mongo import collections


def watch_pending_runs() -> Iterator[dict]:
    """Yield runs that should be started by the daemon.

    In a replica-set-backed Mongo deployment this uses change streams. In
    simpler local environments it falls back to polling.
    """
    cols = collections()
    # This aggregation-style filter is applied by MongoDB's change-stream API.
    # It means "only tell me about inserts/updates/replaces where the latest
    # document has status='pending'".
    pipeline = [
        {
            "$match": {
                "operationType": {"$in": ["insert", "update", "replace"]},
                "fullDocument.status": "pending",
            }
        }
    ]
    try:
        # ``collection.watch(...)`` opens a live stream against MongoDB.
        # The ``with`` block stays open and yields change events as they happen,
        # so this function effectively "listens" forever until the stream dies.
        with cols["pipeline_runs"].watch(
            pipeline, full_document="updateLookup"
        ) as stream:
            for change in stream:
                # ``updateLookup`` gives us the latest full document even for
                # update events, which keeps the daemon logic simple.
                doc = change.get("fullDocument") or {}
                if doc.get("status") == "pending":
                    # Yield the whole run document back to daemon.py, where it
                    # will be turned into an initial graph state and executed.
                    yield doc
    except Exception:
        # Fallback for non-replica-set environments: poll instead of using change streams.
        seen: set[str] = set()
        import time

        while True:
            # In polling mode we repeatedly scan for pending runs. The ``seen``
            # set prevents the same run_id from being yielded over and over.
            for doc in cols["pipeline_runs"].find({"status": "pending"}):
                rid = doc.get("run_id")
                if rid and rid not in seen:
                    seen.add(rid)
                    yield doc
            # Sleep briefly so the fallback loop does not hot-spin and waste CPU.
            time.sleep(1.0)


def watch_user_answers() -> Iterator[dict]:
    """Yield newly inserted user answers for paused runs."""
    cols = collections()
    # For answers we only care about newly inserted documents, because an answer
    # arriving is the event that may allow a paused graph to resume.
    pipeline = [{"$match": {"operationType": "insert"}}]
    try:
        # Just like watch_pending_runs, this opens a live MongoDB stream and
        # keeps yielding answer documents as they are inserted.
        with cols["user_answers"].watch(
            pipeline, full_document="updateLookup"
        ) as stream:
            for change in stream:
                doc = change.get("fullDocument") or {}
                if doc:
                    # Yield one answer document at a time; daemon.py decides
                    # whether enough answers now exist to resume the run.
                    yield doc
    except Exception:
        # The fallback poller deduplicates by run/question id so repeated scans
        # do not trigger duplicate resumes.
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
    """Return answers for a run once every pending question has been answered.

    The daemon resumes only when the full interrupt payload is available. That
    mirrors the API path, which requires all pending questions to be answered in
    one submission.
    """
    cols = collections()
    # First read the questions the agent asked when it interrupted.
    pending = list(cols["pending_questions"].find({"run_id": run_id}))
    qids = {q.get("question_id") for q in pending}
    # Then load whatever answers have arrived so far for those question ids.
    answers = list(
        cols["user_answers"].find({"run_id": run_id, "question_id": {"$in": list(qids)}})
    )
    by_qid = {a.get("question_id"): a for a in answers}
    if len(by_qid) < len(qids):
        # Returning [] is the signal that the daemon should keep waiting rather
        # than resuming the graph with an incomplete answer set.
        return []  # Wait until the full interrupt payload can be resumed in one step.
    out = []
    for q in pending:
        # Rehydrate the answer list in the same order and shape expected by
        # Command(resume=...) in the run service.
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
