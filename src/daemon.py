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
    print("[daemon] watching pipeline_runs for status=pending...")
    for doc in watch_pending_runs():
        if doc.get("run_source") == "webapp":
            continue
        run_id = doc.get("run_id")
        if not run_id:
            continue
        print(f"[daemon] picked up run {run_id}")
        try:
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
            update_run_status(run_id, "failed", error=str(exc))
            continue

        threading.Thread(
            target=run_graph, args=(run_id, initial), daemon=True
        ).start()


def answers_loop():
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
            if run_doc and run_doc.get("run_source") == "webapp":
                continue
        except Exception:
            pass
        answers = collect_answers_for_run(run_id)
        if not answers:
            continue
        print(f"[daemon] resuming run {run_id} with {len(answers)} answers")
        threading.Thread(
            target=resume_graph, args=(run_id, answers), daemon=True
        ).start()


def main():
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
