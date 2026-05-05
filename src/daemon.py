"""Long-running daemon that watches Mongo for externally submitted runs."""

import threading

from dotenv import load_dotenv

from .agent.listener import (
    collect_answers_for_run,
    watch_pending_runs,
    watch_user_answers,
)
from .agent.mongo import collections, ensure_indexes, update_run_status
from .agent.run_service import build_initial_state, resume_graph, run_graph

load_dotenv()


def runs_loop():
    """Watch MongoDB for pending runs and launch each one asynchronously.

    This loop is the daemon's "new work" listener. It consumes documents from
    ``pipeline_runs`` that have been marked ``status="pending"``, converts each
    one into the initial LangGraph state payload, and then starts ``run_graph``
    in its own worker thread so the watcher can immediately go back to
    listening for more runs.
    """
    print("[daemon] watching pipeline_runs for status=pending...")
    for doc in watch_pending_runs():
        # Runs created through the FastAPI path are already enqueued directly by
        # the web process, so the daemon should ignore them to avoid duplicates.
        if doc.get("run_source") == "webapp":
            continue
        run_id = doc.get("run_id")
        if not run_id:
            continue
        print(f"[daemon] picked up run {run_id}")
        try:
            # Translate the MongoDB run document into the same initial state
            # shape used by the API and CLI entrypoints.
            initial = build_initial_state(
                run_id=run_id,
                pipeline_path=doc.get("pipeline_path"),
                source_tables=doc.get("source_tables", []),
                destination_tables=doc.get("destination_tables", []),
                business_context_seed=doc.get("business_context_seed"),
                pipeline_code=doc.get("pipeline_code"),
                seed_source="frontend_seed",
            )
        except Exception as exc:
            # Record the failure on the lifecycle document so the UI can show
            # why the run never started.
            update_run_status(run_id, "failed", error=str(exc))
            continue

        # Execute the graph in a separate worker thread so this watcher remains
        # free to pick up other pending runs immediately.
        threading.Thread(
            target=run_graph, args=(run_id, initial), daemon=True
        ).start()


def answers_loop():
    """Watch MongoDB for user answers and resume paused runs when ready.

    This loop is the daemon's "resume work" listener. It reacts to inserts in
    ``user_answers``, checks whether all pending questions for a run have now
    been answered, and once the interrupt payload is complete starts
    ``resume_graph`` in a worker thread.
    """
    print("[daemon] watching user_answers for resumes...")
    for doc in watch_user_answers():
        run_id = doc.get("run_id")
        if not run_id:
            continue
        try:
            cols = collections()
            run_doc = cols["pipeline_runs"].find_one(
                {"run_id": run_id}, {"_id": 0, "run_source": 1}
            )
            # Web-app-owned runs are resumed by the API path rather than this
            # daemon, so skip them here to avoid double resume attempts.
            if run_doc and run_doc.get("run_source") == "webapp":
                continue
        except Exception:
            pass
        # Only resume once the full set of pending questions has been answered.
        # Partial answers stay in MongoDB until the interrupt payload is complete.
        answers = collect_answers_for_run(run_id)
        if not answers:
            continue
        print(f"[daemon] resuming run {run_id} with {len(answers)} answers")
        # Resume work in a separate thread so the watcher can keep consuming new
        # answer events without being blocked by graph execution.
        threading.Thread(
            target=resume_graph, args=(run_id, answers), daemon=True
        ).start()


def main():
    """Initialise indexes and start the daemon watcher threads."""
    ensure_indexes()
    print("[daemon] graph compiled lazily. Starting watchers.")

    t1 = threading.Thread(target=runs_loop, daemon=True)
    t2 = threading.Thread(target=answers_loop, daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


if __name__ == "__main__":
    main()
