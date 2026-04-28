<!-- Stage 1 documentation for the pipeline QA extractor CLI and architecture. -->
# data-pipeline-qa-agent

Stage 1 provides an LLM-based structural pipeline extractor. It reads one Python pipeline file and an optional DAG/scheduler file, sends focused context to OpenRouter, and returns validated JSON metadata.

## What This Tool Does

- Extracts generic pipeline structure:
  - source tables
  - destination tables
  - referenced columns
  - read/write operations
  - unknowns and warnings
- Extracts technology-specific details based on `--technology`:
  - `databricks`
  - `postgres`
- Validates model output with Pydantic.
- Retries once with a JSON-repair prompt if validation fails.
- Caches extraction output to avoid repeat model calls.
- Captures OpenRouter usage and cost (actual when available, estimated fallback otherwise).

## What This Tool Deliberately Does Not Do

- database connections
- SQL execution
- QA check execution
- agentic investigation loops
- dashboards
- automatic fixes

## Setup

1. Create and activate a virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

2. Install package and dev tools:

```bash
pip install -e ".[dev]"
```

3. Set environment variable:

```bash
export OPENROUTER_API_KEY="your_key_here"
```

Optional OpenRouter headers:

```bash
export OPENROUTER_HTTP_REFERER="https://your-app.example"
export OPENROUTER_X_TITLE="pipeline-qa-extractor"
```

## CLI Usage

```bash
pipeline-qa-extract extract \
  --pipeline-file path/to/pipeline.py \
  --dag-file path/to/dag.py \
  --technology databricks \
  --model openai/gpt-4.1-mini \
  --output output/extraction.json \
  --raw-output-dir output/raw \
  --print-cost
```

### Databricks Example

```bash
pipeline-qa-extract extract \
  --pipeline-file examples/databricks_pipeline.py \
  --technology databricks \
  --output output/databricks_extraction.json
```

### Postgres Example

```bash
pipeline-qa-extract extract \
  --pipeline-file examples/postgres_pipeline.py \
  --technology postgres \
  --output output/postgres_extraction.json
```

## Example Output JSON

```json
{
  "metadata": {
    "pipeline_file_path": "examples/databricks_pipeline.py",
    "pipeline_file_hash": "...",
    "technology": "databricks",
    "model": "openai/gpt-4.1-mini",
    "prompt_version": "v1",
    "extracted_at_utc": "2026-04-27T10:00:00Z"
  },
  "generic_extraction": {
    "pipeline_name": "daily_orders",
    "source_tables": [],
    "destination_tables": [],
    "referenced_columns": [],
    "read_operations": [],
    "write_operations": [],
    "unknowns": [],
    "warnings": []
  },
  "technology_details": {
    "databricks": {
      "spark_reads": [],
      "spark_writes": [],
      "databricks_specific_features": []
    },
    "postgres": null
  },
  "llm_usage": {
    "prompt_tokens": 100,
    "completion_tokens": 250,
    "total_tokens": 350,
    "cached_tokens": null,
    "actual_cost_usd": 0.00021,
    "estimated_cost_usd": null,
    "cost_source": "openrouter_response",
    "pricing_snapshot": {
      "model": "openai/gpt-4.1-mini"
    }
  }
}
```

## Caching

Extraction cache key is built from:

- pipeline file hash
- DAG file hash (if present)
- technology
- model
- prompt version

Cache files are stored at:

- `.pipeline_qa_cache/extractions/{cache_key}.json`

If cache is hit and `--force` is not used:

- extractor returns cached JSON
- OpenRouter is not called
- `llm_usage.cost_source` is set to `cache_hit`

OpenRouter model metadata is cached at:

- `.pipeline_qa_cache/openrouter_models.json`

## OpenRouter Cost Capture

The extractor records usage fields from completion responses when available:

- prompt tokens
- completion tokens
- total tokens
- cached tokens
- cost

If OpenRouter returns actual cost, it is treated as authoritative (`cost_source=openrouter_response`).

If actual cost is missing, the extractor fetches OpenRouter Models API pricing and computes estimated cost (`cost_source=estimated_from_models_api`).

If neither source is available, cost is marked unavailable.

Note: OpenRouter model pricing is fetched from its Models API and usage accounting may provide cost directly; response shapes are handled defensively.

## Stage Scope

This is Stage 1 only (structural extraction). Later stages can use this output for:

- schema enrichment
- semantic interpretation
- deterministic QA planning
