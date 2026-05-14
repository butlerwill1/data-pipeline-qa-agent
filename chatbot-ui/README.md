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

## How the frontend fits together

The UI does not use a bundler or framework. `index.html` loads the CSS and then
loads three JavaScript files in dependency order:

1. `renderers.js` defines escaping helpers and HTML renderers.
2. `api.js` defines fetch wrappers for the FastAPI routes.
3. `chat.js` wires DOM events, owns browser state, calls the API helpers, and
   inserts renderer output into the page.

The backend is always treated as the source of truth. The browser stores only
temporary view state such as the active run ID, polling timer IDs, and sets used
to avoid rendering duplicate question or artifact cards.

## Runtime rendering flow

When an operator submits the run form, `chat.js` builds a payload and calls
`createRun()` from `api.js`. The returned snapshot is passed to `syncSnapshot()`,
which updates the status badge, sidebar summary, pending question forms, and any
available final artifacts.

While a run is active, `pollCurrentRun()` repeatedly calls `getRun()`. Each
response goes through the same `syncSnapshot()` path, so active runs and
historical run replay use the same rendering logic.

Final reports are stored as Markdown by the backend. `renderMarkdownDocument()`
wraps the report in a `.doc-card`, and `markdownToHtml()` uses `marked` to turn
the Markdown into HTML. The visual treatment then comes from `.doc-card` and
`.markdown-body` in `style.css`.

## Layout notes

The app is a fixed-height console. The `body` and `.shell` do not scroll as one
large document; instead, the left `.setup-column` and right `.workspace-column`
scroll independently. This keeps the top header visible and lets the report
workspace move separately from the setup/history panels.

The main report surface is `.chat`. It is hidden until a run or history item is
shown. Dynamic messages are appended into `#messages`, and each message body is
limited to a readable width with `.msg-body`.

If the report background appears to stop while report content continues, inspect
the `.chat` rules in `style.css`. That container controls the large workspace
panel behind the generated report cards.

## Run locally

For a read-only UI that still loads Mongo-backed history and reports:

```bash
make ui
```

This starts the FastAPI web app in read-only mode and opens
`http://127.0.0.1:8000`. Historical runs, findings, executed queries, and final
reports still load through `/api`, but creating runs, submitting answers, and
stop requests are disabled.

For a pure static preview with no API or MongoDB connection at all:

```bash
make ui-static
```

This serves `chatbot-ui/` with Python's standard library static file server and
opens `http://127.0.0.1:3000`. API-backed actions will show backend errors in
this mode because `/api` is not running.

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
