<!-- Summary: Portfolio-facing project overview for the Data QA Agent, including architecture, stack, setup, and usage. -->

# Data Pipeline QA Agent

**MongoDB Agentic Evolution Hackathon — May 2026**

Data Pipeline QA Agent turns pipeline code, table metadata, query evidence, and operator context into a persistent data quality review workflow.

It uses a LangGraph-based reasoning pipeline to:

- read and interpret pipeline logic
- profile source and destination tables
- retrieve prior table understanding from MongoDB Atlas
- generate guardrailed QA checks
- execute those checks against Athena
- interpret the results and produce a final report

The result is a review system that does more than run static SQL tests. It builds a reusable memory of how tables behave, what risks matter, and what evidence supported past QA decisions.

## Screenshots

![Local operator console overview](<QA UI example 1.png>)

![Run review and evidence view](<QA UI example 2.png>)

## Why this project exists

Data quality work is usually fragmented across pipeline code, warehouse metadata, ad hoc SQL, and tribal knowledge from the people who own the data. This project brings those pieces into one workflow.

Instead of treating QA as a flat checklist, the agent builds context first, then uses that context to plan and run checks that are grounded in the actual pipeline and table design. MongoDB Atlas acts as the system of record for run history, findings, reports, pending questions, and versioned table understanding.

## Core capabilities

- **Pipeline-aware QA planning**: parses pipeline code to understand source tables, destination tables, transformations, and implied business logic.
- **Schema- and metadata-grounded checks**: profiles tables from Glue and generates Athena-compatible QA SQL using authoritative schema information.
- **Persistent table memory**: stores versioned table understanding documents in MongoDB Atlas and retrieves prior context through vector search.
- **Human-in-the-loop clarification**: pauses when critical business context is missing, stores questions, and resumes once answers are supplied.
- **Evidence-backed reporting**: stores executed queries, findings, and a final Markdown report for later review in the web app.
- **Local operator UI**: includes a FastAPI-served web interface for browsing runs, reviewing reports, and submitting new runs.

## Architecture

The runtime is a single LangGraph workflow with specialized stages. Each stage contributes to one shared run state, while MongoDB persists both application artefacts and LangGraph checkpoints.

```mermaid
flowchart LR
    Operator["Operator / Reviewer"]
    UI["FastAPI Web UI<br/>HTML / CSS / JavaScript"]
    API["FastAPI API + Run Service"]
    Graph["LangGraph QA Workflow"]
    Mongo["MongoDB Atlas<br/>runs, questions, answers,<br/>findings, reports, table memory,<br/>and graph checkpoints"]
    Glue["AWS Glue Catalog"]
    Athena["AWS Athena"]
    LLM["Claude via OpenRouter API"]
    Voyage["Voyage AI Embeddings"]
    LangSmith["LangSmith Traces"]

    Operator --> UI
    UI --> API
    API --> Graph
    API <--> Mongo
    Graph <--> Mongo
    Graph --> Glue
    Graph --> Athena
    Graph --> LLM
    Graph --> Voyage
    Graph --> LangSmith
```

### Persistence model

MongoDB Atlas stores the project’s durable application state:

- `pipeline_runs`: run lifecycle and current status
- `table_understandings`: versioned table memory, including embeddings for retrieval
- `pending_questions`: questions emitted during a paused run
- `user_answers`: answers submitted through the UI or other external process
- `executed_queries`: every executed QA query with sample results
- `findings`: interpreted pass, warn, and fail observations
- `final_reports`: final Markdown reports and severity summaries

LangGraph checkpoints are stored separately through `MongoDBSaver`, which makes interrupt/resume and state recovery possible.

## Workflow

The workflow starts from pipeline code and table identifiers, then loops through clarification if the system cannot yet produce reliable QA checks.

```mermaid
flowchart TD
    A["load_inputs"] --> B["extract_pipeline_logic"]
    B --> C["profile_tables"]
    C --> D["retrieve_prior_understanding"]
    D --> E["identify_knowledge_gaps"]
    E -->|Important gaps remain| F["ask_business_context"]
    F --> E
    E -->|Enough context gathered| G["update_table_understanding"]
    G --> H["generate_qa_checks"]
    H --> I["run_qa_queries"]
    I --> J["interpret_results"]
    J --> K["write_final_report"]
    K --> L["persist_run"]
```

## Stack

### Application and orchestration

- **Python 3.12**
- **LangGraph** for stateful workflow orchestration
- **FastAPI** for the local API and web app serving layer
- **Uvicorn** as the ASGI server

### Data and persistence

- **MongoDB Atlas** for application persistence and vector retrieval
- **PyMongo** for direct MongoDB access
- **langgraph-checkpoint-mongodb** for graph checkpoint persistence

### Data platform integration

- **AWS Athena** for executing read-only QA SQL
- **AWS Glue Catalog** for authoritative schema metadata
- **S3 / Athena output location** for query results in real runs

### Model and retrieval layer

- **Anthropic Claude via OpenRouter** for reasoning in real mode
- **Voyage AI embeddings** for retrieving relevant prior table understanding
- **LangSmith** for observability and trace inspection

### Frontend

- **Static HTML/CSS/JavaScript** served by the FastAPI app
- **FastAPI-served local operator console** for run submission, history review, evidence inspection, and report reading

## Project structure

```text
chatbot-ui/          Static frontend for the local operator console
src/webapp.py        FastAPI web app and API routes
src/cli.py           CLI entrypoint for running the workflow directly
src/daemon.py        Mongo-watching daemon for external run orchestration
src/agent/graph.py   LangGraph workflow definition
src/agent/nodes/     Workflow stages for extraction, profiling, planning, execution, and reporting
src/agent/mongo.py   MongoDB connection and collection helpers
docs/                Supporting documentation and frontend contract notes
```

## Local setup

### 1. Install dependencies

```bash
make setup
```

This installs `uv`, ensures Python 3.12 is available, syncs the project dependencies, and scaffolds `.env` from `.env.example` if needed.

### 2. Minimum `.env` for dry-run mode

```text
conn_string=mongodb+srv://USER:PASSWORD@cluster.mongodb.net/?appName=Cluster0
MONGO_DB_NAME=qa_agent
DRY_RUN=1
```

Dry-run mode uses realistic mocked outputs for LLM, Glue, Athena, and embeddings, so you can test the full workflow without cloud credentials beyond MongoDB.

### 3. Initialise indexes

```bash
make init
```

## Running the project

### CLI demo run

```bash
make demo
```

This runs the end-to-end workflow in dry-run mode against the configured smart meter example pipeline.

### Full CLI run

```bash
make real
```

This runs the same workflow against real configured services. It requires a complete `.env` with model, AWS, and query-execution settings.

### Full web app

```bash
make web
```

Starts the FastAPI UI/API at `http://127.0.0.1:8000` with writable browser actions enabled.

### Read-only web app

```bash
make ui
```

Starts the web UI in read-only mode. This is useful for reviewing historical runs, reports, findings, and executed queries without allowing new submissions.

### Static UI preview

```bash
make ui-static
```

Serves the frontend only, without the API or MongoDB-backed history.

### Daemon mode

```bash
make daemon
```

Starts the Mongo-watching daemon that resumes externally submitted runs and answers.

## Manual CLI invocation

```bash
uv run python -m src.cli run \
  --pipeline /path/to/transform_daily.py \
  --source-tables catalog.schema.source_table \
  --destination-tables catalog.schema.destination_table \
  --business-context "Daily rollup; should be complete by 9am next day."
```

## Guardrails

Athena query execution is intentionally constrained:

- read-only statements only
- forbidden DDL and DML keywords rejected
- defensive `LIMIT` added to unconstrained `SELECT` statements
- per-query timeout
- bounded result sampling for storage and UI display

These guardrails keep the generated checks inspectable and reduce the risk of unsafe or runaway execution.

## Web UI

The local operator console is designed to make the workflow inspectable rather than opaque. It exposes:

- run submission
- run status and current graph node
- pending clarification questions
- executed query evidence
- historical findings
- final Markdown QA reports

This makes the project suitable both as a backend workflow demonstration and as a user-facing QA review tool.

## Hackathon context

This project was originally built for the **MongoDB Agentic Evolution Hackathon**. The hackathon framing shaped several of the project’s strongest technical ideas:

- using MongoDB Atlas as durable operational memory, not just a logging sink
- treating table understanding as a retrievable asset across runs
- combining workflow state, evidence, and reports into one inspectable system
- building a human-in-the-loop QA process rather than a fire-and-forget script
