# Core extraction orchestration: load files, prompt LLM, validate JSON, compute usage, and cache results.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pipeline_qa_extractor.cache import (
    CACHE_DIR,
    load_cached_extraction,
    load_models_cache,
    save_cached_extraction,
    save_models_cache,
)
from pipeline_qa_extractor.cost import OpenRouterCostTracker
from pipeline_qa_extractor.file_loader import build_input_bundle
from pipeline_qa_extractor.hashing import build_cache_key, sha256_text
from pipeline_qa_extractor.models import (
    ExtractedPayload,
    ExtractionConfig,
    ExtractionMetadata,
    ExtractionResult,
    LlmUsage,
    Technology,
    ValidatedExtractionResult,
    enforce_technology_details,
)
from pipeline_qa_extractor.openrouter_client import OpenRouterClient, try_parse_json
from pipeline_qa_extractor.prompts import PROMPT_VERSION, build_repair_prompt, build_system_prompt, build_user_prompt


class ExtractionError(RuntimeError):
    pass


class PipelineExtractor:
    def __init__(self, client: OpenRouterClient | None = None) -> None:
        self.client = client or OpenRouterClient()

    def run(self, cfg: ExtractionConfig) -> ExtractionResult:
        pipeline_text, dag_text, _ = build_input_bundle(cfg.pipeline_file, cfg.dag_file, cfg.max_input_chars)

        pipeline_hash = sha256_text(pipeline_text)
        dag_hash = sha256_text(dag_text) if dag_text is not None else None

        cache_key = build_cache_key(
            {
                "pipeline_file_hash": pipeline_hash,
                "dag_file_hash": dag_hash,
                "technology": cfg.technology,
                "model": cfg.model,
                "prompt_version": cfg.prompt_version,
            }
        )

        if not cfg.force:
            cached = load_cached_extraction(cache_key)
            if cached:
                cached["llm_usage"]["cost_source"] = "cache_hit"
                result = ValidatedExtractionResult.model_validate(cached)
                return ExtractionResult.model_validate(result.model_dump())

        system_prompt = build_system_prompt(cfg.technology)
        user_prompt = build_user_prompt(cfg.pipeline_file, pipeline_text, cfg.dag_file, dag_text)

        first = self.client.chat_json(model=cfg.model, system_prompt=system_prompt, user_prompt=user_prompt)
        payload, parse_error = self._validate_payload(first.content, cfg.technology)

        raw_dir = Path(cfg.raw_output_dir) if cfg.raw_output_dir else None
        if raw_dir:
            self._save_raw(raw_dir, "initial", first.raw_response)

        if payload is None:
            repair_prompt = build_repair_prompt(parse_error, first.content)
            repaired = self.client.chat_json(model=cfg.model, system_prompt=system_prompt, user_prompt=repair_prompt)
            if raw_dir:
                self._save_raw(raw_dir, "repair", repaired.raw_response)

            payload, second_error = self._validate_payload(repaired.content, cfg.technology)
            if payload is None:
                failure_dir = raw_dir or (CACHE_DIR / "raw_failures")
                self._save_raw(failure_dir, "initial_failure", first.raw_response)
                self._save_raw(failure_dir, "repair_failure", repaired.raw_response)
                raise ExtractionError(
                    "Model output could not be validated after one repair attempt. "
                    f"Initial error: {parse_error}. Repair error: {second_error}"
                )
            raw_response = repaired.raw_response
        else:
            raw_response = first.raw_response

        tracker = OpenRouterCostTracker(model=cfg.model)
        usage = tracker.usage_from_response(raw_response)

        if usage.actual_cost_usd is None:
            models_payload = load_models_cache()
            if models_payload is None:
                models_payload = self.client.fetch_models()
                save_models_cache(models_payload)
            usage = tracker.apply_estimate_if_needed(usage, models_payload)

        result = self._build_result(
            cfg=cfg,
            payload=payload,
            usage=usage,
            pipeline_hash=pipeline_hash,
        )
        save_cached_extraction(cache_key, result.model_dump())
        return result

    def _validate_payload(self, text: str, technology: Technology) -> tuple[ExtractedPayload | None, str]:
        try:
            parsed = try_parse_json(text)
            payload = ExtractedPayload.model_validate(parsed)
            enforce_technology_details(technology, payload.technology_details)
            return payload, ""
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            return None, str(exc)

    def _build_result(
        self,
        cfg: ExtractionConfig,
        payload: ExtractedPayload,
        usage: LlmUsage,
        pipeline_hash: str,
    ) -> ExtractionResult:
        metadata = ExtractionMetadata(
            pipeline_file_path=cfg.pipeline_file,
            pipeline_file_hash=pipeline_hash,
            technology=cfg.technology,
            model=cfg.model,
            prompt_version=cfg.prompt_version or PROMPT_VERSION,
            extracted_at_utc=ExtractionMetadata.now_utc_iso(),
        )

        result = ExtractionResult(
            metadata=metadata,
            generic_extraction=payload.generic_extraction,
            technology_details=payload.technology_details,
            llm_usage=usage,
        )
        ValidatedExtractionResult.model_validate(result.model_dump())
        return result

    def _save_raw(self, raw_output_dir: Path, label: str, raw: dict[str, Any]) -> Path:
        raw_output_dir.mkdir(parents=True, exist_ok=True)
        path = raw_output_dir / f"{label}_response.json"
        path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
        return path
