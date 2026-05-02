# Pipeline QA Agent UI

This folder now contains the phase 1 local operator UI for the Python QA agent in this repo.

It is no longer an Athena demo shell. It expects the repo's FastAPI server and run-oriented API.

## Architecture

The UI talks to the local backend served by `src.webapp`.

Flow:

1. `POST /api/runs`
2. Poll `GET /api/runs/{run_id}`
3. If the agent pauses, submit `POST /api/runs/{run_id}/answers`
4. Review the final markdown report plus executed SQL and sample table results

The UI is also served by the same FastAPI app, so you can run one local server for both the API and the static frontend.

## Files

- `index.html`: page structure
- `style.css`: layout, color system, cards, and responsive behavior
- `api.js`: fetch helpers for the local `/api` contract
- `renderers.js`: HTML renderers for reports, findings, questions, and query samples
- `chat.js`: browser state, polling, run submission, and answer flow

## Run locally

Use the repo virtual environment, then start the FastAPI server:

```bash
source qa-agent-venv/bin/activate
python -m src.webapp
```

Then open:

```text
http://127.0.0.1:8000
```

## API contract

### `POST /api/runs`

Request body:

```json
{
  "pipeline_path": "/Users/you/project/src/transform_daily.py",
  "source_tables": ["catalog.schema.table_a"],
  "destination_tables": ["catalog.schema.table_b"],
  "business_context_seed": "Optional business context"
}
```

Response:

```json
{
  "run": { "...": "..." },
  "pending_questions": [],
  "answered_questions": [],
  "executed_queries": [],
  "findings": [],
  "report": null,
  "documents": [],
  "summary": { "...": "..." }
}
```

### `GET /api/runs/{run_id}`

Returns the full snapshot for the run:

- current run status
- unanswered questions
- answered questions
- executed queries with `result_sample`
- findings
- final report markdown

### `POST /api/runs/{run_id}/answers`

Request body:

```json
{
  "answers": [
    {
      "question_id": "uuid",
      "answer": "Operator answer"
    }
  ]
}
```

### `GET /api/runs/{run_id}/report.md`

Returns the final report markdown document once available.
