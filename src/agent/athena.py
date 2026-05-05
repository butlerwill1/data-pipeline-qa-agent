"""Athena query helpers with read-only validation and runtime guardrails.

The rest of the agent does not talk to boto3 directly. Instead it calls this
module, which enforces a narrow, read-only query policy and normalises the
response into a small record that is safe to store in MongoDB and easy for
later nodes to interpret.
"""

import os
import re
import time

import boto3
from dotenv import load_dotenv

from . import mocks

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")
ATHENA_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
ATHENA_OUTPUT = os.getenv("ATHENA_OUTPUT_LOCATION")
DEFAULT_DB = os.getenv("ATHENA_DATABASE", os.getenv("GLUE_DATABASE", "default"))
QUERY_TIMEOUT = int(os.getenv("ATHENA_TIMEOUT_SEC", "30"))
MAX_BYTES = int(os.getenv("ATHENA_MAX_BYTES", str(200 * 1024 * 1024)))  # 200 MB
MAX_RESULT_ROWS = int(os.getenv("ATHENA_MAX_ROWS", "100"))

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|GRANT|REVOKE|TRUNCATE|MERGE|REPLACE)\b",
    re.IGNORECASE,
)
_SELECT_LIKE = re.compile(r"^\s*(SELECT|WITH|DESCRIBE|DESC|SHOW|EXPLAIN)\b", re.IGNORECASE)

_athena = None


def client():
    """Lazily create and cache the Athena boto3 client.

    Reusing one client keeps the wrapper cheap to call from multiple nodes in a
    single process.
    """
    global _athena
    if _athena is None:
        _athena = boto3.client("athena", region_name=AWS_REGION)
    return _athena


def validate(sql: str) -> tuple[bool, str]:
    """Validate that SQL is read-only and normalise it for bounded execution.

    The return value is ``(ok, payload)`` where ``payload`` is either:
    - the cleaned SQL statement when validation succeeds
    - a rejection reason when validation fails
    """
    if _FORBIDDEN.search(sql):
        return False, "contains forbidden DDL/DML keyword"
    m = _SELECT_LIKE.match(sql)
    if not m:
        return False, "not a SELECT/WITH/DESCRIBE/SHOW/EXPLAIN"
    verb = m.group(1).upper()
    cleaned = sql.rstrip(";").rstrip()
    if verb in ("SELECT", "WITH") and "limit" not in cleaned.lower():
        # Add a defensive limit so an LLM-generated query does not accidentally
        # return an unbounded result set.
        cleaned = f"{cleaned} LIMIT 1000"
    return True, cleaned


def run(sql: str, database: str | None = None) -> dict:
    """Execute a validated Athena query and return a compact result summary.

    The result intentionally keeps only high-signal fields: status, query id,
    runtime, bytes scanned, row count, and a small sample of the rows returned.
    """
    ok, normalised = validate(sql)
    if not ok:
        return {"status": "rejected", "reason": normalised, "sql": sql}
    sql = normalised

    if mocks.is_dry_run():
        return mocks.mock_athena_run(sql)

    db = database or DEFAULT_DB
    # Build the boto3 request incrementally so optional output-location
    # configuration can be applied only when the environment provides it.
    kwargs = {
        "QueryString": sql,
        "QueryExecutionContext": {"Database": db},
        "WorkGroup": ATHENA_WORKGROUP,
    }
    if ATHENA_OUTPUT:
        kwargs["ResultConfiguration"] = {"OutputLocation": ATHENA_OUTPUT}

    started = time.time()
    qid = client().start_query_execution(**kwargs)["QueryExecutionId"]

    state = "RUNNING"
    info = {}
    while state in ("RUNNING", "QUEUED"):
        # Stop runaway queries so the agent does not hang on a bad check.
        if time.time() - started > QUERY_TIMEOUT:
            try:
                client().stop_query_execution(QueryExecutionId=qid)
            except Exception:
                pass
            return {"status": "timeout", "sql": sql, "query_id": qid}
        time.sleep(0.4)
        info = client().get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = info["Status"]["State"]

    if state != "SUCCEEDED":
        return {
            "status": "failed",
            "sql": sql,
            "query_id": qid,
            "error": info["Status"].get("StateChangeReason"),
        }

    bytes_scanned = info["Statistics"].get("DataScannedInBytes", 0)

    # Athena returns the first row as column headers. Convert the remaining rows
    # into dictionaries so downstream nodes can reason over named values.
    rows = client().get_query_results(QueryExecutionId=qid, MaxResults=MAX_RESULT_ROWS)
    raw_rows = rows["ResultSet"]["Rows"]
    headers: list[str] = []
    if raw_rows:
        headers = [c.get("VarCharValue", "") for c in raw_rows[0]["Data"]]
    data = [
        {h: cell.get("VarCharValue") for h, cell in zip(headers, r["Data"])}
        for r in raw_rows[1:]
    ]
    return {
        "status": "ok",
        "sql": sql,
        "query_id": qid,
        "runtime_ms": int(info["Statistics"].get("EngineExecutionTimeInMillis", 0)),
        "bytes_scanned": bytes_scanned,
        "exceeded_byte_cap": bytes_scanned > MAX_BYTES,
        "row_count": len(data),
        "result_sample": data[:25],
    }
