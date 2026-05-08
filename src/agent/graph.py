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

    # Nodes are the actual units of work in the graph. Each node is just a
    # Python function that receives the current shared state and returns a
    # partial state update. In this project, each node corresponds to one stage
    # of the QA workflow such as profiling tables, generating checks, or writing
    # the final report.
    #
    # Defining a node here does not say when it runs, only that it exists and
    # what function LangGraph should call when execution reaches that step.
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

    # Edges define control flow between nodes.
    #
    # You can think of an edge as an arrow from one step to the next:
    # "after node A finishes, go to node B".
    #
    # START and END are special built-in markers from LangGraph:
    # - START means "where execution begins"
    # - END means "the graph is finished"
    g.add_edge(START, "load_inputs")
    g.add_edge("load_inputs", "extract_pipeline_logic")
    g.add_edge("extract_pipeline_logic", "profile_tables")
    g.add_edge("profile_tables", "retrieve_prior_understanding")
    g.add_edge("retrieve_prior_understanding", "identify_knowledge_gaps")

    # Most of the graph is a straight line, but here we add a conditional edge.
    # Instead of always going to one fixed next node, LangGraph calls the
    # router function ``gaps_remain`` and uses the returned string to decide
    # which edge to follow.
    #
    # In other words:
    # - if there are still important unanswered questions, go ask the user
    # - otherwise continue with understanding synthesis
    g.add_conditional_edges(
        "identify_knowledge_gaps",
        gaps_remain,
        {
            "ask_business_context": "ask_business_context",
            "update_table_understanding": "update_table_understanding",
        },
    )

    # This edge creates the feedback loop in the graph. After asking the user
    # for business context and resuming, the graph returns to the gap-checking
    # node to see whether enough clarification has now been gathered.
    g.add_edge("ask_business_context", "identify_knowledge_gaps")

    # Once the graph has enough context, execution becomes linear again:
    # understand tables -> generate checks -> run checks -> interpret evidence
    # -> write report -> mark run complete.
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
    # ``MongoDBSaver`` is LangGraph's checkpoint backend. It is not one of this
    # application's own collections such as ``pipeline_runs`` or
    # ``table_understandings``. Instead, it is the persistence layer LangGraph
    # uses to save the graph's internal execution state between steps.
    #
    # In practice that means:
    # - the current state payload can be recovered after each node runs
    # - interrupt/resume works because paused state is stored durably
    # - ``app.get_state(...)`` can read the latest checkpointed graph state
    #
    # These checkpoint writes go to LangGraph-managed MongoDB collections, not
    # to the application collections returned by ``mongo.collections()``.
    saver = MongoDBSaver(client=get_client(), db_name=db_name)
    # ``g.compile(...)`` turns the graph definition into an executable LangGraph
    # app. Passing ``checkpointer=saver`` tells LangGraph:
    #
    # "whenever this graph advances, persist its internal checkpoint state using
    # this MongoDB-backed saver".
    #
    # So yes, this is one of the places where MongoDB gets written to, but only
    # for LangGraph checkpoint data.
    #
    # It is not the only place MongoDB is written to in this codebase. The node
    # modules and run-service helpers also perform explicit application-level
    # writes such as:
    # - ``pipeline_runs`` lifecycle updates
    # - ``pending_questions`` and ``user_answers``
    # - ``table_understandings``, ``executed_queries``, ``findings``
    # - ``final_reports``
    #
    # Those writes are separate from checkpoint persistence and are done by
    # explicit calls to ``insert_one``, ``update_one``, ``delete_many``, etc.
    return g.compile(checkpointer=saver)
