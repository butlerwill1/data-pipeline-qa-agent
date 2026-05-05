"""LangGraph definition for the end-to-end data QA workflow.

This module is the assembly point for the agent. It wires together the node
modules, defines the one conditional branch in the workflow, and attaches a
MongoDB-backed checkpointer so interrupted or resumed runs keep their state.
"""

import os

from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.graph import END, START, StateGraph

from .mongo import get_client
from .nodes.ask_context import ask_business_context
from .nodes.extract_pipeline import extract_pipeline_logic
from .nodes.generate_checks import generate_qa_checks
from .nodes.identify_gaps import identify_knowledge_gaps
from .nodes.interpret_results import interpret_results
from .nodes.load_inputs import load_inputs
from .nodes.persist_run import persist_run
from .nodes.profile_tables import profile_tables
from .nodes.retrieve_prior import retrieve_prior_understanding
from .nodes.run_queries import run_qa_queries
from .nodes.update_understanding import update_table_understanding
from .nodes.write_report import write_final_report
from .state import State

MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "2"))


def gaps_remain(state: State) -> str:
    """Route back to user context collection while important gaps still remain.

    This router is intentionally simple: if the gap detector still has
    questions and the loop count is below the configured maximum, the graph goes
    back through the interrupt path. Otherwise it moves on to synthesis.
    """
    iter_count = state.get("iteration_count", 0) or 0
    gaps = state.get("knowledge_gaps", []) or []
    if gaps and iter_count < MAX_ITERATIONS:
        return "ask_business_context"
    return "update_table_understanding"


def build_graph() -> StateGraph:
    """Assemble the QA workflow graph and its node transitions."""
    g = StateGraph(State)

    # Register every functional step before defining the edges between them.
    g.add_node("load_inputs", load_inputs)
    g.add_node("extract_pipeline_logic", extract_pipeline_logic)
    g.add_node("profile_tables", profile_tables)
    g.add_node("retrieve_prior_understanding", retrieve_prior_understanding)
    g.add_node("identify_knowledge_gaps", identify_knowledge_gaps)
    g.add_node("ask_business_context", ask_business_context)
    g.add_node("update_table_understanding", update_table_understanding)
    g.add_node("generate_qa_checks", generate_qa_checks)
    g.add_node("run_qa_queries", run_qa_queries)
    g.add_node("interpret_results", interpret_results)
    g.add_node("write_final_report", write_final_report)
    g.add_node("persist_run", persist_run)

    g.add_edge(START, "load_inputs")
    g.add_edge("load_inputs", "extract_pipeline_logic")
    g.add_edge("extract_pipeline_logic", "profile_tables")
    g.add_edge("profile_tables", "retrieve_prior_understanding")
    g.add_edge("retrieve_prior_understanding", "identify_knowledge_gaps")

    # This is the only branching point in the graph. The rest of the workflow
    # is linear once enough context has been gathered.
    g.add_conditional_edges(
        "identify_knowledge_gaps",
        gaps_remain,
        {
            "ask_business_context": "ask_business_context",
            "update_table_understanding": "update_table_understanding",
        },
    )
    g.add_edge("ask_business_context", "identify_knowledge_gaps")
    g.add_edge("update_table_understanding", "generate_qa_checks")
    g.add_edge("generate_qa_checks", "run_qa_queries")
    g.add_edge("run_qa_queries", "interpret_results")
    g.add_edge("interpret_results", "write_final_report")
    g.add_edge("write_final_report", "persist_run")
    g.add_edge("persist_run", END)

    return g


def compiled_graph():
    """Compile the graph with MongoDB-backed checkpoint persistence.

    ``MongoDBSaver`` stores LangGraph's internal checkpoint data in the same
    database cluster as the application's run artefacts, which makes pause,
    resume, and state inspection straightforward.
    """
    g = build_graph()
    db_name = os.getenv("MONGO_DB_NAME", "qa_agent")
    saver = MongoDBSaver(client=get_client(), db_name=db_name)
    return g.compile(checkpointer=saver)
