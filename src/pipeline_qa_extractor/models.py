# Pydantic models defining validated extraction output for generic and technology-specific blocks.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


Technology = Literal["databricks", "postgres"]
Confidence = Literal["high", "medium", "low"]


class ExtractionMetadata(BaseModel):
    pipeline_file_path: str
    pipeline_file_hash: str
    technology: Technology
    model: str
    prompt_version: str
    extracted_at_utc: str

    @staticmethod
    def now_utc_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SourceTable(BaseModel):
    name: str
    evidence_snippet: str
    how_detected: str
    confidence: Confidence


class DestinationTable(BaseModel):
    name: str
    evidence_snippet: str
    how_detected: str
    confidence: Confidence


class ReferencedColumn(BaseModel):
    name: str
    table_if_known: str | None
    context: str
    evidence_snippet: str
    confidence: Confidence


class ReadOperation(BaseModel):
    operation_type: str
    target: str
    evidence_snippet: str
    confidence: Confidence


class WriteOperation(BaseModel):
    operation_type: str
    target: str
    write_disposition: str | None
    evidence_snippet: str
    confidence: Confidence


class GenericExtraction(BaseModel):
    pipeline_name: str | None = None
    source_tables: list[SourceTable] = Field(default_factory=list)
    destination_tables: list[DestinationTable] = Field(default_factory=list)
    referenced_columns: list[ReferencedColumn] = Field(default_factory=list)
    read_operations: list[ReadOperation] = Field(default_factory=list)
    write_operations: list[WriteOperation] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DatabricksSparkRead(BaseModel):
    method: str
    target: str
    evidence_snippet: str
    confidence: Confidence


class DatabricksSparkWrite(BaseModel):
    method: str
    target_table: str
    mode: str | None
    format: str | None
    partition_columns: list[str] = Field(default_factory=list)
    replace_where: str | None
    merge_condition: str | None
    evidence_snippet: str
    confidence: Confidence


class DatabricksFeature(BaseModel):
    feature: str
    evidence_snippet: str
    confidence: Confidence


class DatabricksDetails(BaseModel):
    spark_reads: list[DatabricksSparkRead] = Field(default_factory=list)
    spark_writes: list[DatabricksSparkWrite] = Field(default_factory=list)
    databricks_specific_features: list[DatabricksFeature] = Field(default_factory=list)


class PostgresRead(BaseModel):
    method: str
    target: str
    evidence_snippet: str
    confidence: Confidence


class PostgresWrite(BaseModel):
    method: str
    target_table: str
    conflict_handling: str | None
    returning_columns: list[str] = Field(default_factory=list)
    transaction_usage: str | None
    evidence_snippet: str
    confidence: Confidence


class PostgresFeature(BaseModel):
    feature: str
    evidence_snippet: str
    confidence: Confidence


class PostgresDetails(BaseModel):
    sql_reads: list[PostgresRead] = Field(default_factory=list)
    sql_writes: list[PostgresWrite] = Field(default_factory=list)
    postgres_specific_features: list[PostgresFeature] = Field(default_factory=list)


class TechnologyDetails(BaseModel):
    databricks: DatabricksDetails | None = None
    postgres: PostgresDetails | None = None


class LlmUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int | None = None
    actual_cost_usd: float | None = None
    estimated_cost_usd: float | None = None
    cost_source: str = "unavailable"
    pricing_snapshot: dict[str, Any] = Field(default_factory=dict)


class ExtractedPayload(BaseModel):
    generic_extraction: GenericExtraction
    technology_details: TechnologyDetails


class ExtractionResult(BaseModel):
    metadata: ExtractionMetadata
    generic_extraction: GenericExtraction
    technology_details: TechnologyDetails
    llm_usage: LlmUsage


class ExtractionConfig(BaseModel):
    pipeline_file: str
    dag_file: str | None = None
    technology: Technology
    model: str = "openai/gpt-4.1-mini"
    output: str
    force: bool = False
    print_cost: bool = False
    raw_output_dir: str | None = None
    max_input_chars: int = 80000
    prompt_version: str = "v1"


def enforce_technology_details(technology: Technology, details: TechnologyDetails) -> None:
    if technology == "databricks":
        if details.databricks is None:
            raise ValueError("technology_details.databricks must be present for technology=databricks")
        if details.postgres is not None:
            raise ValueError("technology_details.postgres must be null for technology=databricks")
        return

    if details.postgres is None:
        raise ValueError("technology_details.postgres must be present for technology=postgres")
    if details.databricks is not None:
        raise ValueError("technology_details.databricks must be null for technology=postgres")


class ValidatedExtractionResult(ExtractionResult):
    @model_validator(mode="after")
    def _validate_technology_details(self) -> "ValidatedExtractionResult":
        enforce_technology_details(self.metadata.technology, self.technology_details)
        return self
