"""Canned responses used when DRY_RUN=1.

Lets us exercise the LangGraph wiring, MongoDB writes, interrupt/resume,
and Atlas Vector Search without needing Bedrock, Athena, Glue, or Voyage
credentials. The mocks are tuned to the UK smart meter pipeline so the
output looks realistic in a demo.
"""

from __future__ import annotations

import os
import random


def is_dry_run() -> bool:
    return os.getenv("DRY_RUN") == "1"


_TABLE_HINTS = {
    "raw_external_smart_meter": {
        "role": "source_table",
        "description": "Bronze parquet of UK half-hourly smart meter consumption from the external Weave Energy dataset.",
        "grain": ["dataset_id", "lv_feeder_unique_id", "data_collection_log_timestamp"],
        "ts": "data_collection_log_timestamp",
        "important": ["dataset_id", "dno_alias", "total_consumption_active_import"],
    },
    "silver_smart_meter_half_hourly_clean": {
        "role": "destination_table",
        "description": "Silver layer with cleaned half-hourly readings, partitioned by collection_date.",
        "grain": ["composite_feeder_id", "data_collection_log_timestamp"],
        "ts": "data_collection_log_timestamp",
        "important": ["composite_feeder_id", "consumption_per_active_device", "collection_date"],
    },
    "gold_peak_demand_substation_day": {
        "role": "destination_table",
        "description": "Gold-layer peak demand per substation per day, used for downstream reporting.",
        "grain": ["secondary_substation_unique_id", "consumption_date"],
        "ts": "peak_timestamp",
        "important": ["secondary_substation_unique_id", "peak_consumption", "daily_total_consumption"],
    },
}


def _short(table_id: str) -> str:
    return table_id.split(".")[-1]


def mock_extract_pipeline_logic(source_tables: list[str], dest_tables: list[str]) -> dict:
    return {
        "confirmed_source_tables": [
            {"id": t, "evidence": f"spark.read.parquet referencing {t} location"}
            for t in source_tables
        ],
        "confirmed_destination_tables": [
            {"id": t, "evidence": f"df.write.partitionBy.saveAsTable({t})"}
            for t in dest_tables
        ],
        "transformations": [
            "filter rows where data_collection_log_timestamp is not null",
            "derive hour_of_day, minute_of_hour, half_hour_slot from timestamp",
            "compute consumption_per_active_device",
            "group by composite_feeder_id and half-hour slot",
        ],
        "filters": ["aggregated_device_count_active > 0"],
        "joins": [],
        "aggregations": ["SUM(total_consumption_active_import) per substation per day"],
        "candidate_grain_columns": ["composite_feeder_id", "data_collection_log_timestamp"],
        "candidate_timestamp_columns": ["data_collection_log_timestamp", "peak_timestamp"],
        "business_logic_observations": [
            "Daily idempotent re-processing by overwriting only the target collection_date partition.",
            "Bronze read-only; pipeline does not modify the source.",
        ],
    }


def mock_identify_gaps(business_context: list[dict]) -> dict:
    if any("9am" in (bc.get("answer") or "").lower() for bc in business_context):
        return {"gaps": []}
    return {
        "gaps": [
            {
                "table_id": "energy_smart_meter.silver_smart_meter_half_hourly_clean",
                "question": "Is it normal for the latest collection_date to be incomplete during the morning, or should it be complete by a specific cutoff?",
                "why_it_matters": "Drives the freshness check threshold; without this, freshness alarms will be noisy.",
            }
        ]
    }


def mock_update_understanding(table_id: str, business_context: list[dict]) -> dict:
    short = _short(table_id)
    hint = _TABLE_HINTS.get(short, {
        "role": "table",
        "description": f"Inferred description for {table_id}.",
        "grain": ["unknown"],
        "ts": "ts",
        "important": [],
    })

    freshness = {
        "cadence": "daily",
        "expected_lag": "by 09:00 next day",
        "confidence": "high" if business_context else "medium",
        "source": "user_answer" if business_context else "pipeline_code",
    }

    return {
        "table_id": table_id,
        "business_description": hint["description"],
        "grain": {
            "columns": hint["grain"],
            "confidence": "medium",
            "evidence": [f"GROUP BY in pipeline references {hint['grain']}"],
        },
        "freshness_expectation": freshness,
        "important_columns": [
            {
                "name": c,
                "role": "key" if c.endswith("_id") else "metric",
                "nullable_expected": False,
                "confidence": "high",
                "evidence": [f"appears in pipeline transformations for {table_id}"],
            }
            for c in hint["important"]
        ],
        "known_risks": [
            "Same-day partition may be incomplete during morning processing.",
            "External Bronze source can drop coverage for some DNOs without notice.",
        ],
        "source_evidence": [
            {"type": "pipeline_code", "content": f"pipeline writes to {table_id}"},
        ] + [
            {"type": "user_answer", "content": bc.get("answer", "")}
            for bc in business_context if bc.get("answer")
        ],
    }


def mock_generate_checks(table_understanding: dict) -> dict:
    checks = []
    for table_id, _u in table_understanding.items():
        short = _short(table_id)
        db, _, name = table_id.partition(".")
        checks.append({
            "id": f"chk_freshness_{short}",
            "name": f"Freshness of {short}",
            "intent": "Confirm latest data lands within expected lag.",
            "target_table": table_id,
            "sql": f'SELECT MAX(data_collection_log_timestamp) AS latest FROM "{db}"."{name}"',
            "risk_level": "low",
            "expected_outcome": "latest within last 24 hours",
            "category": "freshness",
        })
        checks.append({
            "id": f"chk_rows_by_day_{short}",
            "name": f"Row count by day for {short}",
            "intent": "Spot day-over-day drops.",
            "target_table": table_id,
            "sql": f'SELECT date_trunc(\'day\', data_collection_log_timestamp) d, COUNT(*) c FROM "{db}"."{name}" GROUP BY 1 ORDER BY 1 DESC LIMIT 14',
            "risk_level": "low",
            "expected_outcome": "stable counts day over day",
            "category": "row_count",
        })
    return {"checks": checks[:6]}


def mock_interpret_results(executed: list[dict]) -> dict:
    findings = []
    for q in executed:
        if q.get("category") == "freshness":
            findings.append({
                "title": f"Freshness within expectation for {q.get('target_table')}",
                "severity": "pass",
                "evidence": "latest timestamp is within the last 24 hours per query result.",
                "recommended_action": "no action",
                "related_check": q.get("check_name"),
                "related_table": q.get("target_table"),
            })
        elif q.get("category") == "row_count":
            findings.append({
                "title": f"Day-over-day row counts stable for {q.get('target_table')}",
                "severity": "pass",
                "evidence": "no day in the trailing 14 deviates more than 5% from the median.",
                "recommended_action": "no action",
                "related_check": q.get("check_name"),
                "related_table": q.get("target_table"),
            })
    return {"findings": findings}


def mock_final_report(table_understanding: dict, findings: list[dict]) -> str:
    sev = {"pass": 0, "warn": 0, "fail": 0}
    for f in findings:
        sev[f.get("severity", "pass")] = sev.get(f.get("severity", "pass"), 0) + 1
    table_lines = "\n".join(
        f"- **{tid}** — {u.get('business_description', '')}"
        for tid, u in table_understanding.items()
    )
    findings_lines = "\n".join(
        f"- [{f.get('severity').upper()}] {f.get('title')} — {f.get('evidence')}"
        for f in findings
    )
    return f"""# Data QA Report

## Executive Summary

Reviewed {len(table_understanding)} tables across the smart meter pipeline. Severity summary: {sev['pass']} pass, {sev['warn']} warn, {sev['fail']} fail.

## Tables Reviewed

{table_lines}

## Findings

{findings_lines or '_No findings produced in this run._'}

## Recommended Actions

- Continue monitoring freshness; alert if lag exceeds 24h.
- Maintain row-count baselines per day for trend detection.
"""


def mock_glue_metadata(table_id: str) -> dict:
    short = _short(table_id)
    db, _, name = (table_id.partition(".") if "." in table_id else ("energy_smart_meter", "", table_id))
    cols_by_table = {
        "raw_external_smart_meter": [
            "dataset_id", "dno_alias", "aggregated_device_count_active",
            "total_consumption_active_import", "data_collection_log_timestamp",
            "geometry", "secondary_substation_unique_id", "lv_feeder_unique_id", "bbox",
        ],
        "silver_smart_meter_half_hourly_clean": [
            "dataset_id", "dno_alias", "aggregated_device_count_active",
            "total_consumption_active_import", "data_collection_log_timestamp",
            "geometry", "secondary_substation_unique_id", "lv_feeder_unique_id", "bbox",
            "hour_of_day", "minute_of_hour", "half_hour_slot", "day_of_week",
            "is_weekend", "composite_feeder_id", "consumption_per_active_device",
            "collection_date",
        ],
        "gold_peak_demand_substation_day": [
            "dno_alias", "secondary_substation_unique_id", "peak_consumption",
            "peak_timestamp", "daily_total_consumption", "avg_half_hour_consumption",
            "consumption_date",
        ],
    }
    cols = cols_by_table.get(short, ["id", "ts"])
    return {
        "table_id": table_id,
        "database": db or "energy_smart_meter",
        "name": name or short,
        "location": f"s3://weave-smart-meter-data/portfolio/{short}/",
        "columns": [{"name": c, "type": "string", "comment": None} for c in cols],
        "partition_keys": [{"name": "collection_date", "type": "date"}] if "silver" in short else (
            [{"name": "consumption_date", "type": "date"}] if "gold" in short else []
        ),
        "table_type": "EXTERNAL_TABLE",
        "input_format": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
    }


def mock_athena_run(sql: str) -> dict:
    sql_lower = sql.lower()
    if "count(*)" in sql_lower and "group by" not in sql_lower:
        rows = [{"row_count": "12480394"}]
    elif "max(" in sql_lower and "min(" in sql_lower:
        rows = [{"min_ts": "2024-01-01 00:00:00.000", "max_ts": "2026-05-01 23:30:00.000"}]
    elif "max(" in sql_lower:
        rows = [{"latest": "2026-05-01 23:30:00.000"}]
    elif "group by" in sql_lower and "count(*)" in sql_lower:
        rows = [
            {"d": f"2026-04-{30 - i:02d}", "c": str(518400 + random.randint(-5000, 5000))}
            for i in range(14)
        ]
    else:
        rows = [{"value": "ok"}]

    return {
        "status": "ok",
        "sql": sql,
        "query_id": "mock-" + str(random.randint(1000, 9999)),
        "runtime_ms": random.randint(120, 800),
        "bytes_scanned": random.randint(50_000, 5_000_000),
        "exceeded_byte_cap": False,
        "row_count": len(rows),
        "result_sample": rows,
    }


def mock_embedding(_text: str) -> list[float]:
    rng = random.Random(_text)
    return [rng.uniform(-0.1, 0.1) for _ in range(1024)]
