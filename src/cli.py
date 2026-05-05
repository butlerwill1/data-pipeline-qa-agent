"""Command-line entrypoint for running and initialising QA agent workflows."""

import argparse
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langgraph.types import Command

from .agent.graph import compiled_graph
from .agent.mongo import collections, ensure_indexes

load_dotenv()


def cmd_init(_args):
    """Create MongoDB indexes required by the agent runtime."""
    ensure_indexes()
    print("Mongo indexes created.")


def cmd_run(args):
    """Run the graph from the CLI and handle any interrupt-driven questions."""
    pipeline_text = Path(args.pipeline).read_text()

    initial = {
        "run_id": args.run_id or str(uuid.uuid4()),
        "pipeline_path": args.pipeline,
        "pipeline_code": pipeline_text,
        "source_tables": args.source_tables or [],
        "destination_tables": args.destination_tables or [],
    }
    if args.business_context:
        initial["user_business_context"] = [
            {
                "answer": args.business_context,
                "source": "cli_seed",
            }
        ]

    print(f"\n▶  Starting QA run {initial['run_id']}")
    print(f"   pipeline:  {args.pipeline}")
    print(f"   sources:   {initial['source_tables']}")
    print(f"   dests:     {initial['destination_tables']}\n")

    app = compiled_graph()
    config = {"configurable": {"thread_id": initial["run_id"]}}

    last_state: dict = {}
    for event in app.stream(initial, config=config, stream_mode="values"):
        last_state = event
        _print_progress(event)

    snapshot = app.get_state(config)
    while snapshot.next:
        last_state = _handle_interrupt(app, config, initial["run_id"], args.auto_answer)
        for event in app.stream(
            Command(resume=last_state["__resumed_with__"]),
            config=config,
            stream_mode="values",
        ):
            last_state = event
            _print_progress(event)
        snapshot = app.get_state(config)

    print("\n=== Final Report ===\n")
    print(last_state.get("final_report") or "(no report produced)")


def _print_progress(event: dict):
    """Render a compact progress summary for the current graph state."""
    transitions = []
    if event.get("extracted_logic"):
        transitions.append("extracted")
    if event.get("table_profiles"):
        transitions.append(f"profiled:{len(event['table_profiles'])}")
    if event.get("table_understanding"):
        transitions.append(f"understanding:{len(event['table_understanding'])}")
    if event.get("candidate_checks"):
        transitions.append(f"checks:{len(event['candidate_checks'])}")
    if event.get("executed_queries"):
        transitions.append(f"executed:{len(event['executed_queries'])}")
    if event.get("findings"):
        transitions.append(f"findings:{len(event['findings'])}")
    if event.get("final_report"):
        transitions.append("report")
    if transitions:
        print(f"   · {' '.join(transitions)}")


def _handle_interrupt(app, config, run_id: str, auto_answer: str | None) -> dict:
    """Collect answers for pending questions and shape them for graph resume."""
    cols = collections()
    questions = list(cols["pending_questions"].find({"run_id": run_id}, {"_id": 0}))

    print("\n— Agent paused for user input —")
    if not questions:
        print("(no pending questions found in Mongo)")
        return {"__resumed_with__": []}

    answers = []
    for q in questions:
        print(f"\nQ ({q.get('table_id')}): {q.get('question')}")
        if q.get("why_it_matters"):
            print(f"   why: {q['why_it_matters']}")
        ans = auto_answer if auto_answer else input("Your answer: ").strip()
        answers.append(
            {
                "question_id": q.get("question_id"),
                "table_id": q.get("table_id"),
                "question": q.get("question"),
                "answer": ans,
            }
        )

    return {"__resumed_with__": answers}


def main():
    """Parse CLI arguments and dispatch to the selected subcommand."""
    p = argparse.ArgumentParser(prog="qa-agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Run the QA agent against a pipeline")
    r.add_argument("--pipeline", required=True, help="Path to the pipeline source file")
    r.add_argument("--source-tables", nargs="*", default=[])
    r.add_argument("--destination-tables", nargs="*", default=[])
    r.add_argument("--business-context", help="Free-text seed business context")
    r.add_argument("--run-id", help="Optional run id (defaults to a fresh uuid)")
    r.add_argument(
        "--auto-answer",
        help="Auto-answer interrupts with this string (for testing)",
    )
    r.set_defaults(func=cmd_run)

    init = sub.add_parser("init", help="Create indexes in Mongo")
    init.set_defaults(func=cmd_init)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
