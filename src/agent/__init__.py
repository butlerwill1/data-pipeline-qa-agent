"""Core agent package for graph orchestration, integrations, and mocks.

This package contains the non-UI runtime for the QA agent:
- service wrappers around external systems such as Athena, Glue, MongoDB, and LLMs
- the LangGraph workflow definition and shared state contract
- orchestration helpers used by the CLI, daemon, and FastAPI app
- dry-run fixtures that simulate external services during demos
"""
