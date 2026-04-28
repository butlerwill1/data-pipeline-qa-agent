# Usage and cost accounting for OpenRouter responses with model-pricing fallback estimates.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pipeline_qa_extractor.models import LlmUsage


@dataclass
class OpenRouterCostTracker:
    model: str

    def usage_from_response(self, raw_response: dict[str, Any]) -> LlmUsage:
        usage = raw_response.get("usage") or {}

        prompt_tokens = _int_or_zero(usage.get("prompt_tokens"))
        completion_tokens = _int_or_zero(usage.get("completion_tokens"))
        total_tokens = _int_or_zero(usage.get("total_tokens"))

        if total_tokens == 0 and (prompt_tokens > 0 or completion_tokens > 0):
            total_tokens = prompt_tokens + completion_tokens

        cached_tokens = _extract_cached_tokens(usage)
        actual_cost = _extract_actual_cost(raw_response, usage)

        return LlmUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            actual_cost_usd=actual_cost,
            estimated_cost_usd=None,
            cost_source="openrouter_response" if actual_cost is not None else "unavailable",
            pricing_snapshot={"model": self.model},
        )

    def apply_estimate_if_needed(self, usage: LlmUsage, models_payload: dict[str, Any] | None) -> LlmUsage:
        if usage.actual_cost_usd is not None:
            return usage

        model_info = _find_model(models_payload, self.model)
        pricing = (model_info or {}).get("pricing") or {}

        prompt_rate = _float_or_none(pricing.get("prompt"))
        completion_rate = _float_or_none(pricing.get("completion"))

        if prompt_rate is None or completion_rate is None:
            usage.cost_source = "unavailable"
            usage.pricing_snapshot = {"model": self.model, "pricing": pricing}
            return usage

        estimated = (usage.prompt_tokens * prompt_rate) + (usage.completion_tokens * completion_rate)
        usage.estimated_cost_usd = round(estimated, 12)
        usage.cost_source = "estimated_from_models_api"
        usage.pricing_snapshot = {
            "model": self.model,
            "pricing": {
                "prompt": prompt_rate,
                "completion": completion_rate,
            },
        }
        return usage


def _find_model(models_payload: dict[str, Any] | None, model_id: str) -> dict[str, Any] | None:
    if not models_payload:
        return None
    models = models_payload.get("data")
    if not isinstance(models, list):
        return None
    for model in models:
        if isinstance(model, dict) and model.get("id") == model_id:
            return model
    return None


def _extract_cached_tokens(usage: dict[str, Any]) -> int | None:
    prompt_details = usage.get("prompt_tokens_details") or {}
    cached = prompt_details.get("cached_tokens")
    if cached is None:
        cached = usage.get("cached_tokens")
    return _int_or_none(cached)


def _extract_actual_cost(raw_response: dict[str, Any], usage: dict[str, Any]) -> float | None:
    for candidate in (
        usage.get("cost"),
        raw_response.get("cost"),
        raw_response.get("total_cost"),
    ):
        parsed = _float_or_none(candidate)
        if parsed is not None:
            return parsed
    return None


def _int_or_zero(value: Any) -> int:
    parsed = _int_or_none(value)
    return parsed or 0


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
