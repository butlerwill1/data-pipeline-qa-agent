# AWS setup (Glue + Athena)

The QA agent uses three AWS services to inspect the smart meter pipeline's tables. This doc explains what each does, what credentials we need, and how to wire everything up in ~10 minutes.

## What the three pieces do

**S3** holds the actual data. The smart meter pipeline writes parquet files into `s3://weave-smart-meter-data/portfolio/...`. Just files on disk.

**AWS Glue Data Catalog** is a metadata directory. It maps table names like `energy_smart_meter.silver_smart_meter_half_hourly_clean` to their column definitions, partition keys, and S3 locations. No data, just a phone book.

**Athena** is a serverless SQL engine. Give it SQL; it consults Glue for the schema, reads the parquet from S3, and returns results. Pay per byte scanned. No infrastructure to spin up.

## How the agent uses them

| File | Service | What it does |
|------|---------|--------------|
| `src/agent/glue.py` | Glue Catalog | Fetches schema, partitions, S3 location for each known table. Cheap and free. |
| `src/agent/athena.py` | Athena + S3 | Runs validated read-only SQL: row counts, freshness checks, null %, day-over-day. Capped at 30s per query, 200MB scanned. |

Our queries are read-only by validation; the executor strips DDL/DML and auto-injects `LIMIT` on un-bounded SELECTs.

## What we need from butlerwill1

The Glue tables and Athena workgroup live in butlerwill1's AWS account (deployed via the smart meter pipeline's Terraform). Our agent needs credentials that can call Athena and Glue in that account.

**Fastest path: an IAM user with read access.** Five minutes in butlerwill1's AWS console.

### Step-by-step for butlerwill1

1. **IAM** → **Users** → **Create user** → name `qa-agent-hackathon`. No console access needed.
2. **Attach policies directly:**
   - `AmazonAthenaFullAccess` (read is enough but the managed policy is simplest)
   - `AWSGlueConsoleFullAccess` (or just `AWSGlueServiceRole` for read)
   - Plus the inline policy below for S3 read on the relevant buckets:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::weave-smart-meter-data",
        "arn:aws:s3:::weave-smart-meter-data/*",
        "arn:aws:s3:::smart-meter-athena-results",
        "arn:aws:s3:::smart-meter-athena-results/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::smart-meter-athena-results",
        "arn:aws:s3:::smart-meter-athena-results/*"
      ]
    }
  ]
}
```

The Athena results bucket needs write so Athena can dump query outputs there.

3. **Create access key** for that user. Choose "Other" / "Application running outside AWS" if prompted.
4. Hand the **Access Key ID** and **Secret Access Key** to whoever runs the agent.

## What Solomon (or anyone running the agent) does

Add these to `.env`:

```
AWS_REGION=eu-west-2
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
GLUE_DATABASE=energy_smart_meter
ATHENA_DATABASE=energy_smart_meter
ATHENA_WORKGROUP=energy-smart-meter-pipeline-dev-athena
ATHENA_OUTPUT_LOCATION=s3://smart-meter-athena-results/
```

## Verify it works

Quick smoke test, no agent needed:

```bash
uv run python -c "
from src.agent.glue import get_table_metadata
m = get_table_metadata('energy_smart_meter.silver_smart_meter_half_hourly_clean')
print('cols:', [c['name'] for c in m.get('columns', [])])
print('location:', m.get('location'))
"
```

Then a real Athena query:

```bash
uv run python -c "
from src.agent.athena import run
r = run('SELECT COUNT(*) AS n FROM energy_smart_meter.silver_smart_meter_half_hourly_clean')
print(r)
"
```

If the second one returns a row count under 5 seconds, AWS is wired correctly and the agent can run end-to-end against real data.

## Fallback

If AWS access doesn't land in time, set `DRY_RUN=1` in `.env`. Glue and Athena both return realistic mock responses tuned to the smart meter tables. The graph runs end-to-end against real Mongo, with synthetic-but-believable query results. The demo still works; the numbers just aren't from S3.

## Tables in scope

| Table | Layer | Partitions |
|-------|-------|-----------|
| `energy_smart_meter.raw_external_smart_meter` | Bronze (read-only external) | none |
| `energy_smart_meter.silver_smart_meter_half_hourly_clean` | Silver | `collection_date` |
| `energy_smart_meter.gold_peak_demand_substation_day` | Gold | `consumption_date` |
| `energy_smart_meter.gold_profile_*` | Gold (other) | varies |
| `energy_smart_meter.run_log` | Pipeline run log | none |
