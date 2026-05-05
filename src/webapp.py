"""FastAPI application exposing health, run, answer, and report endpoints."""

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent.mongo import ensure_indexes
from .agent.run_service import (
    create_run,
    get_run_snapshot,
    list_runs,
    request_stop,
    submit_answers,
)

UI_DIR = Path(__file__).resolve().parents[1] / "chatbot-ui"


class RunCreateRequest(BaseModel):
    """Payload used to start a new QA run."""

    pipeline_path: str = Field(min_length=1)
    source_tables: list[str] = Field(default_factory=list)
    destination_tables: list[str] = Field(default_factory=list)
    business_context_seed: str | None = None
    pipeline_code: str | None = None


class RunAnswer(BaseModel):
    """Single answer submitted for a pending run question."""

    question_id: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class RunAnswersRequest(BaseModel):
    """Batch answer payload for resuming an interrupted run."""

    answers: list[RunAnswer] = Field(min_length=1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ensure required MongoDB indexes exist when the API starts."""
    ensure_indexes()
    yield


app = FastAPI(
    title="Data Pipeline QA Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    """Return a lightweight health response for the API and bundled UI."""
    return {
        "status": "ok",
        "ui_available": UI_DIR.is_dir(),
    }


@app.get("/api/runs")
def runs(limit: int = 20) -> dict:
    """List recent runs with a bounded page size."""
    safe_limit = max(1, min(limit, 50))
    return {"runs": list_runs(limit=safe_limit)}


@app.post("/api/runs")
def create_run_route(body: RunCreateRequest) -> dict:
    """Create a new run and return its initial snapshot."""
    try:
        run_id = create_run(
            pipeline_path=body.pipeline_path,
            source_tables=body.source_tables,
            destination_tables=body.destination_tables,
            business_context_seed=body.business_context_seed,
            pipeline_code=body.pipeline_code,
        )
        return get_run_snapshot(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}")
def run_snapshot(run_id: str) -> dict:
    """Fetch the current snapshot for a specific run."""
    try:
        return get_run_snapshot(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/runs/{run_id}/answers")
def answer_run_questions(run_id: str, body: RunAnswersRequest) -> dict:
    """Store answers for a paused run and enqueue graph resumption."""
    try:
        submit_answers(
            run_id=run_id,
            answers=[answer.model_dump() for answer in body.answers],
        )
        return get_run_snapshot(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str) -> dict:
    """Request that a running or paused QA run stop."""
    try:
        return request_stop(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}/report.md", response_class=PlainTextResponse)
def report_markdown(run_id: str) -> str:
    """Return the final Markdown report for a completed run."""
    try:
        snapshot = get_run_snapshot(run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    report = snapshot.get("report")
    if not report:
        raise HTTPException(status_code=404, detail="This run does not have a final report yet.")
    return report.get("markdown", "")


if UI_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="chatbot-ui")


def main() -> None:
    """Run the local FastAPI server for the QA agent web experience."""
    uvicorn.run(
        "src.webapp:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
