"""LangGraph node implementations used by the QA workflow.

Each module in this package owns one step in the graph. Nodes receive the
shared ``State`` dictionary, perform one focused piece of work, and return a
partial update that LangGraph merges back into the run state.
"""
