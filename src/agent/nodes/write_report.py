"""Render the final Markdown report for a QA run.

This node turns the run's accumulated evidence into a single human-readable
summary. The report is intentionally concise and uses only successfully parsed
table understandings plus the interpreted findings from the previous node.
"""

from .. import mocks
from ..llm import call
from ..mongo import collections, now_utc, update_run_status
from ..state import State


def write_final_report(state: State) -> dict:
    """Create and persist the final Markdown report for the run.

    The report is stored separately from findings so consumers can fetch either
    the granular artefacts or the final narrative summary.
    """
    update_run_status(state["run_id"], "running", current_node="write_final_report")

    full_understanding = state.get("table_understanding", {}) or {}
    understanding = {
        tid: u for tid, u in full_understanding.items() if not u.get("parsing_failed")
    }
    skipped_tables = [
        tid for tid, u in full_understanding.items() if u.get("parsing_failed")
    ]
    findings = state.get("findings", [])
    executed = state.get("executed_queries", [])

    if mocks.is_dry_run():
        # Dry-run mode bypasses the model so demo environments can still show a
        # realistic end-to-end report without external credentials.
        md = mocks.mock_final_report(understanding, findings)
    else:
        system = (
            "You write a concise, evidence-backed data QA report in Markdown. Sections: "
            "Executive Summary, Tables Reviewed, Checks Performed, Findings (ordered by "
            "severity, with evidence), Recommended Actions. Cite specific values from "
            "query results in the evidence. Keep under 600 words."
        )
        skipped_note = (
            f"\n\nTables that could not be characterised (skipped, do not invent findings about them): {skipped_tables}"
            if skipped_tables else ""
        )
        user = (
            f"Table understandings: {understanding}{skipped_note}\n\n"
            f"Findings: {findings}\n\n"
            "Executed queries summary (without large samples): "
            f"{[{k: v for k, v in q.items() if k != 'result_sample'} for q in executed]}"
        )
        md = call(system, user, max_tokens=4096)

    # Store a small rollup beside the markdown so list views do not need to
    # parse the full report text to show pass/warn/fail counts.
    severity_summary = {
        "pass": sum(1 for f in findings if f.get("severity") == "pass"),
        "warn": sum(1 for f in findings if f.get("severity") == "warn"),
        "fail": sum(1 for f in findings if f.get("severity") == "fail"),
    }

    cols = collections()
    cols["final_reports"].update_one(
        {"run_id": state["run_id"]},
        {
            "$set": {
                "run_id": state["run_id"],
                "markdown": md,
                "severity_summary": severity_summary,
                "generated_at": now_utc(),
            }
        },
        upsert=True,
    )

    return {"final_report": md}
