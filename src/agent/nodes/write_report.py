from .. import mocks
from ..llm import call
from ..mongo import collections, now_utc, update_run_status
from ..state import State


def write_final_report(state: State) -> dict:
    update_run_status(state["run_id"], "running", current_node="write_final_report")

    understanding = state.get("table_understanding", {})
    findings = state.get("findings", [])
    executed = state.get("executed_queries", [])

    if mocks.is_dry_run():
        md = mocks.mock_final_report(understanding, findings)
    else:
        system = (
            "You write a concise, evidence-backed data QA report in Markdown. Sections: "
            "Executive Summary, Tables Reviewed, Checks Performed, Findings (ordered by "
            "severity, with evidence), Recommended Actions. Cite specific values from "
            "query results in the evidence. Keep under 600 words."
        )
        user = (
            f"Table understandings: {understanding}\n\n"
            f"Findings: {findings}\n\n"
            "Executed queries summary (without large samples): "
            f"{[{k: v for k, v in q.items() if k != 'result_sample'} for q in executed]}"
        )
        md = call(system, user, max_tokens=4096)

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
