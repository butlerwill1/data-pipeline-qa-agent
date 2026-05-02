"""Long-running daemon that the team's frontend talks to via Mongo.

Watches `pipeline_runs` for new pending runs and `user_answers` for resumes.
The frontend never imports Python; it just writes Mongo documents and reads
them back.
"""

import threading
from pathlib import Path

from dotenv import load_dotenv
from langgraph.types import Command

from .agent.graph import compiled_graph
from .agent.listener import (
    collect_answers_for_run,
    watch_pending_runs,
    watch_user_answers,
)
from .agent.mongo import ensure_indexes, update_run_status

load_dotenv()


def _resolve_pipeline_code(doc: dict) -> str:
    if doc.get("pipeline_code"):
        return doc["pipeline_code"]
    path = doc.get("pipeline_path")
    if path and Path(path).is_file():
        return Path(path).read_text()
    return ""


def _run_graph(app, run_id: str, initial: dict) -> None:
    config = {"configurable": {"thread_id": run_id}}
    try:
        for _ in app.stream(initial, config=config, stream_mode="values"):
            pass
    except Exception as e:
        update_run_status(run_id, "failed", error=str(e))


def _resume_graph(app, run_id: str, answers: list[dict]) -> None:
    config = {"configurable": {"thread_id": run_id}}
    try:
        for _ in app.stream(
            Command(resume=answers), config=config, stream_mode="values"
        ):
            pass
    except Exception as e:
        update_run_status(run_id, "failed", error=str(e))


def runs_loop(app):
    print("[daemon] watching pipeline_runs for status=pending...")
    for doc in watch_pending_runs():
        run_id = doc.get("run_id")
        if not run_id:
            continue
        print(f"[daemon] picked up run {run_id}")
        initial = {
            "run_id": run_id,
            "pipeline_path": doc.get("pipeline_path"),
            "pipeline_code": _resolve_pipeline_code(doc),
            "source_tables": doc.get("source_tables", []),
            "destination_tables": doc.get("destination_tables", []),
        }
        if doc.get("business_context_seed"):
            initial["user_business_context"] = [
                {"answer": doc["business_context_seed"], "source": "frontend_seed"}
            ]
        threading.Thread(
            target=_run_graph, args=(app, run_id, initial), daemon=True
        ).start()


def answers_loop(app):
    print("[daemon] watching user_answers for resumes...")
    for doc in watch_user_answers():
        run_id = doc.get("run_id")
        if not run_id:
            continue
        answers = collect_answers_for_run(run_id)
        if not answers:
            continue
        print(f"[daemon] resuming run {run_id} with {len(answers)} answers")
        threading.Thread(
            target=_resume_graph, args=(app, run_id, answers), daemon=True
        ).start()


def main():
    ensure_indexes()
    app = compiled_graph()
    print("[daemon] graph compiled. Starting watchers.")

    t1 = threading.Thread(target=runs_loop, args=(app,), daemon=True)
    t2 = threading.Thread(target=answers_loop, args=(app,), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


if __name__ == "__main__":
    main()
