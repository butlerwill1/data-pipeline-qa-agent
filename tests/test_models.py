# Tests for core extraction schema validation and technology-specific constraints.
"""Unit tests for model defaults and technology detail validation constraints."""
import pytest

from pipeline_qa_extractor.models import (
    DatabricksDetails,
    GenericExtraction,
    PostgresDetails,
    TechnologyDetails,
    enforce_technology_details,
)


def test_technology_validation_requires_selected_block() -> None:
    """Selected technology block should validate when non-selected block is null."""
    details = TechnologyDetails(databricks=DatabricksDetails(), postgres=None)
    enforce_technology_details("databricks", details)


def test_technology_validation_rejects_wrong_block_population() -> None:
    """Validation should fail when both technology blocks are populated."""
    details = TechnologyDetails(databricks=DatabricksDetails(), postgres=PostgresDetails())
    with pytest.raises(ValueError):
        enforce_technology_details("databricks", details)


def test_generic_extraction_defaults() -> None:
    """Generic extraction should initialize empty collection fields."""
    payload = GenericExtraction()
    assert payload.source_tables == []
    assert payload.destination_tables == []
    assert payload.unknowns == []
    assert payload.warnings == []


def test_validated_result_accepts_minimal_databricks_payload() -> None:
    """Minimal valid databricks result should pass post-validation checks."""
    from pipeline_qa_extractor.models import LlmUsage, ExtractionMetadata, ValidatedExtractionResult

    result = ValidatedExtractionResult(
        metadata=ExtractionMetadata(
            pipeline_file_path="pipeline.py",
            pipeline_file_hash="hash",
            technology="databricks",
            model="openai/gpt-4.1-mini",
            prompt_version="v1",
            extracted_at_utc="2026-04-27T00:00:00Z",
        ),
        generic_extraction=GenericExtraction(),
        technology_details=TechnologyDetails(databricks=DatabricksDetails(), postgres=None),
        llm_usage=LlmUsage(),
    )

    assert result.metadata.technology == "databricks"
