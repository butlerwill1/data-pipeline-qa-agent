# Summary: Shared run orchestration and snapshot helpers for the web app and daemon.
import threading
import uuid
from pathlib import Path

from langgraph.types import Command

from .graph import compiled_graph
from .mongo import collections, now_utc, update_run_status

_app = None
_app_lock = threading.Lock()
_active_runs: set[str] = set()
_active_runs_lock = threading.Lock()
TERMINAL_STATUSES = {"complete", "failed", "stopped"}


def _graph():
    global _app
    with _app_lock:
        if _app is None:
            _app = compiled_graph()
    return _app


def _claim_run(run_id: str) -> bool:
    with _active_runs_lock:
        if run_id in _active_runs:
            return False
        _active_runs.add(run_id)
        return True


def _release_run(run_id: str) -> None:
    with _active_runs_lock:
        _active_runs.discard(run_id)


def is_run_active(run_id: str) -> bool:
    with _active_runs_lock:
        return run_id in _active_runs


def _is_stop_requested(run_id: str) -> bool:
    cols = collections()
    run_doc = cols["pipeline_runs"].find_one(
        {"run_id": run_id}, {"_id": 0, "stop_requested": 1}
    )
    return bool(run_doc and run_doc.get("stop_requested"))


def _finalise_stopped_run(run_id: str) -> None:
    cols = collections()
    cols["pending_questions"].delete_many({"run_id": run_id})
    update_run_status(
        run_id,
        "stopped",
        current_node="stopped_by_user",
        stopped_at=now_utc(),
        stop_requested=False,
    )


def _resolve_pipeline_code(pipeline_path: str | None, pipeline_code: str | None) -> str:
    if pipeline_code:
        return pipeline_code
    if pipeline_path and Path(pipeline_path).is_file():
        return Path(pipeline_path).read_text(encoding="utf-8")
    raise FileNotFoundError("Pipeline file not found. Provide a valid pipeline_path or pipeline_code.")


def build_initial_state(
    *,
    run_id: str,
    pipeline_path: str | None,
    source_tables: list[str],
    destination_tables: list[str],
    business_context_seed: str | None = None,
    pipeline_code: str | None = None,
    seed_source: str = "webapp_seed",
) -> dict:
    initial = {
        "run_id": run_id,
        "pipeline_path": pipeline_path,
        "pipeline_code": _resolve_pipeline_code(pipeline_path, pipeline_code),
        "source_tables": source_tables,
        "destination_tables": destination_tables,
    }
    if business_context_seed:
        initial["user_business_context"] = [
            {"answer": business_context_seed, "source": seed_source}
        ]
    return initial


def run_graph(run_id: str, initial: dict) -> None:
    config = {"configurable": {"thread_id": run_id}}
    try:
        for _ in _graph().stream(initial, config=config, stream_mode="values"):
            if _is_stop_requested(run_id):
                _finalise_stopped_run(run_id)
                return
    except Exception as exc:
        update_run_status(run_id, "failed", error=str(exc))


def resume_graph(run_id: str, answers: list[dict]) -> None:
    config = {"configurable": {"thread_id": run_id}}
    try:
        for _ in _graph().stream(
            Command(resume=answers), config=config, stream_mode="values"
        ):
            if _is_stop_requested(run_id):
                _finalise_stopped_run(run_id)
                return
    except Exception as exc:
        update_run_status(run_id, "failed", error=str(exc))


def enqueue_graph_run(run_id: str, initial: dict) -> bool:
    if not _claim_run(run_id):
        return False

    def _target() -> None:
        try:
            run_graph(run_id, initial)
        finally:
            _release_run(run_id)

    threading.Thread(target=_target, daemon=True).start()
    return True


def enqueue_graph_resume(run_id: str, answers: list[dict]) -> bool:
    if not _claim_run(run_id):
        return False

    def _target() -> None:
        try:
            resume_graph(run_id, answers)
        finally:
            _release_run(run_id)

    threading.Thread(target=_target, daemon=True).start()
    return True


def create_run(
    *,
    pipeline_path: str,
    source_tables: list[str],
    destination_tables: list[str],
    business_context_seed: str | None = None,
    pipeline_code: str | None = None,
    run_source: str = "webapp",
) -> str:
    run_id = str(uuid.uuid4())
    initial = build_initial_state(
        run_id=run_id,
        pipeline_path=pipeline_path,
        source_tables=source_tables,
        destination_tables=destination_tables,
        business_context_seed=business_context_seed,
        pipeline_code=pipeline_code,
    )

    cols = collections()
    cols["pipeline_runs"].update_one(
        {"run_id": run_id},
        {
            "$set": {
                "run_id": run_id,
                "pipeline_path": pipeline_path,
                "source_tables": source_tables,
                "destination_tables": destination_tables,
                "business_context_seed": business_context_seed,
                "status": "submitted",
                "current_node": "queued",
                "run_source": run_source,
                "stop_requested": False,
                "created_at": now_utc(),
                "updated_at": now_utc(),
            }
        },
        upsert=True,
    )

    if not enqueue_graph_run(run_id, initial):
        raise RuntimeError(f"Run {run_id} is already active.")

    return run_id


def list_runs(limit: int = 20) -> list[dict]:
    cols = collections()
    cursor = cols["pipeline_runs"].find(
        {},
        {
            "_id": 0,
            "run_id": 1,
            "pipeline_path": 1,
            "status": 1,
            "current_node": 1,
            "started_at": 1,
            "updated_at": 1,
            "completed_at": 1,
            "error": 1,
        },
    ).sort([("started_at", -1), ("updated_at", -1)]).limit(limit)

    runs = []
    for doc in cursor:
        report = cols["final_reports"].find_one(
            {"run_id": doc["run_id"]}, {"_id": 0, "severity_summary": 1}
        )
        doc["severity_summary"] = (
            report.get("severity_summary") if report else {"pass": 0, "warn": 0, "fail": 0}
        )
        doc["is_active"] = is_run_active(doc["run_id"])
        runs.append(doc)
    return runs


def _answered_questions(run_id: str) -> list[dict]:
    cols = collections()
    return list(
        cols["user_answers"]
        .find({"run_id": run_id}, {"_id": 0})
        .sort("answered_at", 1)
    )


def _unanswered_questions(run_id: str) -> list[dict]:
    cols = collections()
    answered_ids = {
        a.get("question_id")
        for a in cols["user_answers"].find(
            {"run_id": run_id}, {"_id": 0, "question_id": 1}
        )
    }
    pending = list(
        cols["pending_questions"]
        .find({"run_id": run_id}, {"_id": 0})
        .sort("created_at", 1)
    )
    return [q for q in pending if q.get("question_id") not in answered_ids]


def get_run_snapshot(run_id: str) -> dict:
    cols = collections()
    run_doc = cols["pipeline_runs"].find_one({"run_id": run_id}, {"_id": 0})
    if not run_doc:
        raise LookupError(f"Run {run_id} was not found.")

    answered = _answered_questions(run_id)
    pending = _unanswered_questions(run_id)
    executed_queries = list(
        cols["executed_queries"]
        .find({"run_id": run_id}, {"_id": 0})
        .sort("executed_at", 1)
    )
    findings = list(
        cols["findings"].find({"run_id": run_id}, {"_id": 0}).sort("created_at", 1)
    )
    report = cols["final_reports"].find_one({"run_id": run_id}, {"_id": 0})

    documents = []
    if report:
        documents.append(
            {
                "kind": "report_markdown",
                "title": "Final QA report",
                "download_url": f"/api/runs/{run_id}/report.md",
                "generated_at": report.get("generated_at"),
            }
        )

    return {
        "run": run_doc,
        "pending_questions": pending,
        "answered_questions": answered,
        "executed_queries": executed_queries,
        "findings": findings,
        "report": report,
        "documents": documents,
        "summary": {
            "is_active": is_run_active(run_id),
            "pending_questions": len(pending),
            "answered_questions": len(answered),
            "executed_queries": len(executed_queries),
            "findings": len(findings),
            "severity_summary": (
                report.get("severity_summary")
                if report
                else {"pass": 0, "warn": 0, "fail": 0}
            ),
        },
    }


def submit_answers(
    *,
    run_id: str,
    answers: list[dict],
    answer_source: str = "webapp",
) -> dict:
    snapshot = get_run_snapshot(run_id)
    pending = snapshot["pending_questions"]
    if not pending:
        raise ValueError("This run does not have any pending questions.")

    pending_by_id = {q["question_id"]: q for q in pending}
    provided_by_id = {a.get("question_id"): a for a in answers}

    missing = [qid for qid in pending_by_id if qid not in provided_by_id]
    if missing:
        raise ValueError("All pending questions must be answered in a single submission.")

    normalised_answers = []
    cols = collections()
    for question_id, question in pending_by_id.items():
        raw_answer = str(provided_by_id[question_id].get("answer", "")).strip()
        if not raw_answer:
            raise ValueError("Every answer must be non-empty.")

        stored = {
            "run_id": run_id,
            "question_id": question_id,
            "table_id": question.get("table_id"),
            "question": question.get("question"),
            "answer": raw_answer,
            "answered_at": now_utc(),
            "source": answer_source,
        }
        cols["user_answers"].update_one(
            {"question_id": question_id}, {"$set": stored}, upsert=True
        )
        normalised_answers.append(
            {
                "question_id": question_id,
                "table_id": question.get("table_id"),
                "question": question.get("question"),
                "answer": raw_answer,
            }
        )

    if not enqueue_graph_resume(run_id, normalised_answers):
        raise RuntimeError(f"Run {run_id} is already active.")

    return get_run_snapshot(run_id)


def request_stop(run_id: str) -> dict:
    cols = collections()
    run_doc = cols["pipeline_runs"].find_one({"run_id": run_id}, {"_id": 0})
    if not run_doc:
        raise LookupError(f"Run {run_id} was not found.")

    status = run_doc.get("status")
    if status in TERMINAL_STATUSES:
        return get_run_snapshot(run_id)

    if status == "awaiting_user" or not is_run_active(run_id):
        _finalise_stopped_run(run_id)
        return get_run_snapshot(run_id)

    update_run_status(
        run_id,
        "stopping",
        stop_requested=True,
        stop_requested_at=now_utc(),
    )
    return get_run_snapshot(run_id)
