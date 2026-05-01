# Tests for technology-specific prompt template selection and non-selected null enforcement text.
"""Unit tests for prompt-template routing by selected extraction technology."""
from pipeline_qa_extractor.prompts import build_system_prompt


def test_databricks_prompt_includes_databricks_template() -> None:
    """Databricks prompt should include Spark details and null postgres block."""
    prompt = build_system_prompt("databricks")
    assert '"spark_reads"' in prompt
    assert '"postgres": null' in prompt


def test_postgres_prompt_includes_postgres_template() -> None:
    """Postgres prompt should include SQL details and null databricks block."""
    prompt = build_system_prompt("postgres")
    assert '"sql_reads"' in prompt
    assert '"databricks": null' in prompt
