"""Shared typed state contract passed between LangGraph nodes.

The graph uses a single mutable logical state. Each node receives some subset
of these fields and returns a partial update, which LangGraph merges back into
the checkpointed run state.
"""

from typing import TypedDict, Optional


class State(TypedDict, total=False):
    """State payload accumulated across the QA workflow.

    Fields fall into a few categories:
    - run identity and input material
    - intermediate reasoning artefacts
    - user clarification context
    - generated checks, execution results, and final report output
    """

    run_id: str
    pipeline_path: str
    pipeline_code: str
    source_tables: list[str]
    destination_tables: list[str]
    business_context_seed: Optional[str]

    extracted_logic: Optional[dict]
    table_profiles: dict[str, dict]
    prior_context: dict[str, list[dict]]
    table_understanding: dict[str, dict]

    knowledge_gaps: list[dict]
    user_business_context: list[dict]
    iteration_count: int

    candidate_checks: list[dict]
    executed_queries: list[dict]
    findings: list[dict]
    final_report: Optional[str]
