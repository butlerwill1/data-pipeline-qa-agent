# Data QA Agent

**MongoDB Agentic Evolution Hackathon — May 2026**

A LangGraph data QA agent that builds persistent, evidence-backed business and technical understanding of data tables from pipeline code, profiling queries, and user-provided business context, then uses that understanding to generate and run guardrailed QA checks automatically. MongoDB is the agent's brain: every table understanding is a versioned document, retrievable across runs via Atlas Vector Search.

## Theme

**Multi-Agent Collaboration.** Specialised reasoning nodes (extractor, profiler, interrogator, planner, executor, interpreter) collaborate through a shared MongoDB knowledge base. The `table_understandings` collection is the medium of collaboration; every node reads from and writes to it.

## Stack

- Python 3.12, `uv`
- LangGraph + `langgraph-checkpoint-mongodb` (`MongoDBSaver` for state)
- Anthropic Claude Sonnet 4.6 via Amazon Bedrock
- MongoDB Atlas (M10 sandbox, vector search enabled)
- AWS Athena + Glue Catalog + S3 (query execution and schema metadata)
- Voyage AI embeddings
- LangSmith observability

## Setup

```bash
uv sync
cp .env.example .env  # fill in the secrets
uv run python -m src.cli init  # create Mongo indexes
```

## Run

CLI (rehearsal / debug):

```bash
uv run python -m src.cli run \
  --pipeline ../uk-smart-meter-data/energy-smart-meter-pipeline/src/transform_daily.py \
  --source-tables energy_smart_meter.raw_external_smart_meter \
  --destination-tables energy_smart_meter.silver_smart_meter_half_hourly_clean energy_smart_meter.gold_peak_demand_substation_day \
  --business-context "Daily UK smart meter half-hourly consumption rollup; should be complete by 9am next day."
```

Daemon (frontend-driven):

```bash
uv run python -m src.daemon
# Frontend inserts a doc into `pipeline_runs` with status="pending" and the daemon picks it up.
```

## Architecture

```
load_inputs
  → extract_pipeline_logic
  → profile_tables
  → retrieve_prior_understanding   (Atlas Vector Search over past table_understandings)
  → identify_knowledge_gaps
       ↓
  (gaps_remain & iter < MAX_ITERATIONS) ?
       yes → ask_business_context (interrupt for user input)
              → identify_knowledge_gaps  (loop)
       no  → update_table_understanding
              → generate_qa_checks
              → run_qa_queries           (guardrailed Athena execution)
              → interpret_results
              → write_final_report
              → persist_run → END
```

## Mongo collections

See [docs/frontend-contract.md](docs/frontend-contract.md) for the document shapes.

| Collection | Purpose |
|------------|---------|
| `pipeline_runs` | Run lifecycle |
| `table_understandings` | Versioned, evidence-backed table memory (vector-indexed) |
| `pending_questions` | Questions emitted on agent interrupt |
| `user_answers` | Frontend writes answers here; daemon resumes |
| `executed_queries` | All Athena queries with results |
| `findings` | Severity-tagged findings |
| `final_reports` | Markdown report per run |
| LangGraph checkpoints | Auto-managed by `MongoDBSaver` |

## Guardrails on query execution

- Read-only verbs only (`SELECT`/`WITH`/`DESCRIBE`/`SHOW`/`EXPLAIN`)
- Statement-level forbid list for DDL/DML
- Auto-`LIMIT 1000` if a `SELECT` lacks one
- 30-second statement timeout
- Per-query bytes-scanned cap (configurable)

## Theme map

| Hackathon ask | How we satisfy it |
|---------------|-------------------|
| MongoDB Atlas required | Atlas M10 holds checkpoint state, table memory, run state, queries, findings, reports. Vector search retrieves prior table understandings. |
| AWS required | Bedrock for Claude inference; Athena for SQL execution; Glue Catalog for schema metadata. |
| Multi-Agent Collaboration | Specialised nodes share state through Mongo; understanding emerges from cross-node contributions. |
| LangGraph | Stateful graph with conditional edges, checkpointing, and human-in-the-loop `interrupt()`. |
| LangSmith | Auto-trace every run; debugging surface and trace inspection during demo. |
