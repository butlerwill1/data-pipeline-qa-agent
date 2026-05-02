# Frontend ↔ Agent Contract

The frontend never imports Python. It only reads and writes MongoDB documents in the Atlas Sandbox.

## Database

`MONGO_DB_NAME` (default `qa_agent`)

## Collections written by the agent (frontend reads)

### `pipeline_runs`

```json
{
  "run_id": "uuid",
  "pipeline_path": "string",
  "source_tables": ["db.table"],
  "destination_tables": ["db.table"],
  "status": "pending|running|awaiting_user|complete|failed",
  "current_node": "string",
  "started_at": "datetime",
  "completed_at": "datetime",
  "updated_at": "datetime",
  "error": "string?"
}
```

### `table_understandings`

Versioned: every run inserts a new document; sort by `version` desc to get latest.

```json
{
  "run_id": "uuid",
  "table_id": "db.table",
  "version": 1,
  "business_description": "string",
  "grain": {
    "columns": ["string"],
    "confidence": "high|medium|low",
    "evidence": ["string"]
  },
  "freshness_expectation": {
    "cadence": "string",
    "expected_lag": "string",
    "confidence": "high|medium|low",
    "source": "string"
  },
  "important_columns": [
    {
      "name": "string",
      "role": "string",
      "nullable_expected": false,
      "confidence": "high|medium|low",
      "evidence": ["string"]
    }
  ],
  "known_risks": ["string"],
  "source_evidence": [
    {"type": "pipeline_code|user_answer|query_result|prior_understanding", "content": "string"}
  ],
  "embedding": "[float, ...] (1024 dims, voyage-3) — vector index on this field",
  "updated_at": "datetime"
}
```

### `pending_questions`

Inserted when the agent pauses for user input. Frontend surfaces these in the UI.

```json
{
  "run_id": "uuid",
  "question_id": "uuid",
  "table_id": "db.table",
  "question": "string",
  "why_it_matters": "string",
  "created_at": "datetime"
}
```

### `executed_queries`

```json
{
  "run_id": "uuid",
  "query_id": "uuid",
  "check_name": "string",
  "purpose": "string",
  "category": "schema|freshness|row_count|null_check|duplicate_grain|reconciliation|aggregation_sanity|business_rule",
  "target_table": "db.table",
  "sql": "string (validated, possibly LIMIT-amended)",
  "status": "ok|rejected|timeout|failed",
  "runtime_ms": 0,
  "row_count": 0,
  "result_sample": [{"col": "value"}],
  "error": "string?",
  "executed_at": "datetime"
}
```

### `findings`

```json
{
  "run_id": "uuid",
  "title": "string",
  "severity": "pass|warn|fail",
  "evidence": "string",
  "recommended_action": "string",
  "related_check": "string",
  "related_table": "db.table",
  "created_at": "datetime"
}
```

### `final_reports`

```json
{
  "run_id": "uuid",
  "markdown": "string (the full report)",
  "severity_summary": {"pass": 0, "warn": 0, "fail": 0},
  "generated_at": "datetime"
}
```

### LangGraph checkpoint collections

Managed automatically by `MongoDBSaver` (collections `checkpoints`, `checkpoint_writes`). Frontend can ignore.

## Collections written by the frontend (agent watches)

### `pipeline_runs` (insert to start a run)

Frontend inserts a new doc with `status: "pending"`:

```json
{
  "run_id": "uuid (frontend-generated or omitted)",
  "pipeline_path": "string (path readable to the daemon)",
  "pipeline_code": "string (alternative to pipeline_path; full source as a string)",
  "source_tables": ["db.table"],
  "destination_tables": ["db.table"],
  "business_context_seed": "string (optional)",
  "status": "pending"
}
```

The daemon picks it up via change stream, sets `status: running`, and runs the graph.

### `user_answers` (insert to resume a paused run)

Frontend inserts one doc per question answered:

```json
{
  "run_id": "uuid",
  "question_id": "uuid (matches pending_questions.question_id)",
  "answer": "string",
  "answered_at": "datetime"
}
```

Once all questions for a run are answered, the daemon resumes the graph.

## Indexes (created at startup by `python -m src.cli init`)

- `pipeline_runs.status`
- `pipeline_runs.run_id` (unique)
- `pending_questions.{run_id, question_id}` (unique compound)
- `user_answers.question_id`
- `table_understandings.table_id`
- `executed_queries.run_id`
- `findings.run_id`
- `final_reports.run_id` (unique)

**Manual:** create the Atlas Vector Search index `table_understandings_vec` on `table_understandings.embedding` (1024 dimensions, cosine similarity).
