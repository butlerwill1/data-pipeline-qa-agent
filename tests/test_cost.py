# Tests for OpenRouter usage extraction and estimated cost fallback logic.
"""Unit tests for usage parsing and pricing-based cost fallback."""
from pipeline_qa_extractor.cost import OpenRouterCostTracker


def test_actual_cost_is_authoritative_when_present() -> None:
    """Cost in response payload should be used directly when present."""
    tracker = OpenRouterCostTracker(model="openai/gpt-4.1-mini")
    usage = tracker.usage_from_response(
        {
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.123,
            }
        }
    )

    assert usage.actual_cost_usd == 0.123
    assert usage.cost_source == "openrouter_response"


def test_estimated_cost_from_models_api_when_cost_missing() -> None:
    """Estimator should use model pricing when authoritative cost is absent."""
    tracker = OpenRouterCostTracker(model="openai/gpt-4.1-mini")
    usage = tracker.usage_from_response(
        {
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
            }
        }
    )

    estimated = tracker.apply_estimate_if_needed(
        usage,
        {
            "data": [
                {
                    "id": "openai/gpt-4.1-mini",
                    "pricing": {
                        "prompt": "0.000001",
                        "completion": "0.000002",
                    },
                }
            ]
        },
    )

    assert estimated.actual_cost_usd is None
    assert estimated.estimated_cost_usd == 0.002
    assert estimated.cost_source == "estimated_from_models_api"
