"""LLM client selection plus freeform and structured response helpers.

The graph relies heavily on structured model outputs. This module centralises
provider selection, client caching, dry-run behavior, and the JSON-parsing
logic needed to keep the rest of the codebase provider-agnostic.
"""

import json
import os

from anthropic import Anthropic, AnthropicBedrock
from dotenv import load_dotenv
from openai import OpenAI

from . import mocks

load_dotenv()


def _provider() -> str:
    """Choose the active LLM provider based on environment configuration.

    The selection order prefers an explicit override first, then Bedrock, then
    OpenRouter, and finally direct Anthropic.
    """
    explicit = os.getenv("LLM_PROVIDER")
    if explicit:
        return explicit.lower()
    if os.getenv("USE_BEDROCK", "1") == "1":
        return "bedrock"
    if os.getenv("OPENROUTER_API_KEY"):
        return "openrouter"
    return "anthropic"


BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "anthropic.claude-sonnet-4-5-20250929-v2:0")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
OPENROUTER_BASE = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

_clients: dict[str, object] = {}


def _client(provider: str):
    """Create and cache a client for the requested provider.

    Different providers expose slightly different client objects, so callers use
    ``call`` and ``call_structured`` instead of touching this directly.
    """
    if provider in _clients:
        return _clients[provider]
    if provider == "bedrock":
        c = AnthropicBedrock(aws_region=os.getenv("AWS_REGION", "us-east-1"))
    elif provider == "anthropic":
        c = Anthropic()
    elif provider == "openrouter":
        c = OpenAI(api_key=os.getenv("OPENROUTER_API_KEY"), base_url=OPENROUTER_BASE)
    else:
        raise RuntimeError(f"unknown LLM_PROVIDER: {provider}")
    _clients[provider] = c
    return c


def call(system: str, user: str, max_tokens: int = 2048, model: str | None = None) -> str:
    """Send a freeform prompt to the configured model provider.

    Args:
        system: High-level role and behavioral instructions.
        user: Task-specific request and evidence payload.
        max_tokens: Maximum output token budget.
        model: Optional provider-specific model override.
    """
    if mocks.is_dry_run():
        return _mock_freeform(system, user)

    provider = _provider()
    if provider == "openrouter":
        # OpenRouter exposes an OpenAI-compatible chat-completions surface.
        m = model or OPENROUTER_MODEL
        resp = _client(provider).chat.completions.create(
            model=m,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    m = model or (BEDROCK_MODEL if provider == "bedrock" else ANTHROPIC_MODEL)
    # Anthropic and Bedrock share the messages API shape, so they can use the
    # same call path once the model name is chosen.
    resp = _client(provider).messages.create(
        model=m,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _strip_fence(raw: str) -> str:
    """Remove surrounding Markdown fences from model output when present.

    Some providers or prompt variants still wrap JSON in code fences even when
    asked not to. This helper normalises that before JSON parsing.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        first_newline = raw.find("\n")
        if first_newline != -1:
            raw = raw[first_newline + 1 :]
        if raw.endswith("```"):
            raw = raw[: -3]
    return raw.strip()


def call_structured(system: str, user: str, schema_hint: str, max_tokens: int = 2048) -> dict:
    """Asks the model to emit JSON matching a schema hint and parses it.

    On OpenRouter we use the API's JSON mode (``response_format=json_object``),
    which guarantees syntactic validity at the provider level. On
    Bedrock/Anthropic we fall back to ask-nicely-and-parse with bracket
    recovery.
    """
    if mocks.is_dry_run():
        return _mock_structured(system, user, schema_hint)

    provider = _provider()
    # Extend the system prompt with explicit output constraints so each node can
    # keep its task-specific instructions separate from the JSON-only contract.
    extended_system = (
        f"{system}\n\n"
        f"Respond with valid JSON only matching this shape:\n{schema_hint}\n"
        "No prose. No markdown fences. Just JSON."
    )

    if provider == "openrouter":
        # Prefer the provider's native JSON mode when it exists.
        resp = _client(provider).chat.completions.create(
            model=OPENROUTER_MODEL,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": extended_system},
                {"role": "user", "content": user},
            ],
        )
        raw = _strip_fence((resp.choices[0].message.content or "").strip())
    else:
        raw = _strip_fence(call(extended_system, user, max_tokens=max_tokens))

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to salvage the first JSON object or array from an otherwise chatty response.
        s = raw.find("{")
        e = raw.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(raw[s : e + 1])
            except json.JSONDecodeError:
                pass
        s = raw.find("[")
        e = raw.rfind("]")
        if s >= 0 and e > s:
            try:
                return json.loads(raw[s : e + 1])
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse JSON from model output: {raw[:200]}")


# ---- mock dispatch (DRY_RUN=1) ----

def _mock_freeform(system: str, user: str) -> str:
    """Route freeform prompts to deterministic dry-run fixtures."""
    if "QA report in Markdown" in system or "Executive Summary" in system:
        return mocks.mock_final_report({}, [])
    return "Mocked response."


def _mock_structured(system: str, user: str, schema_hint: str) -> dict:
    """Route structured prompts to deterministic dry-run fixtures.

    The dispatch rules are intentionally lightweight. They inspect the prompt
    shape to infer which node is asking and then return the matching canned
    payload from ``mocks.py``.
    """
    text = (system + " " + schema_hint).lower()
    if "candidate_grain_columns" in text:
        srcs = _between(user, "Source tables (claimed by the operator):", "\n")
        dsts = _between(user, "Destination tables (claimed by the operator):", "\n")
        return mocks.mock_extract_pipeline_logic(_listify(srcs), _listify(dsts))
    if '"gaps"' in schema_hint:
        bc_str = _between(user, "Business context already gathered:", "\n\n")
        bc = [{"answer": bc_str}] if bc_str else []
        return mocks.mock_identify_gaps(bc)
    if "freshness_expectation" in text and "important_columns" in text:
        table_id = _extract_table_id(user)
        bc_str = _between(user, "User business context (Q&A):", "\n\n")
        bc = [{"answer": bc_str}] if bc_str and bc_str != "[]" else []
        return mocks.mock_update_understanding(table_id, bc)
    if "checks" in text and ("expected_outcome" in text or "risk_level" in text):
        return mocks.mock_generate_checks(_recover_understandings(user))
    if "findings" in text and "severity" in text:
        return mocks.mock_interpret_results(_recover_executed(user))
    return {}


def _between(text: str, start: str, end: str) -> str:
    """Extract text between two markers, tolerating a missing end marker."""
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    if j < 0:
        return text[i + len(start):].strip()
    return text[i + len(start):j].strip()


def _listify(s: str) -> list[str]:
    """Turn a lightweight bracketed string list into Python strings."""
    s = s.strip().strip("[]")
    if not s:
        return []
    return [p.strip().strip("'\"") for p in s.split(",") if p.strip()]


def _extract_table_id(user: str) -> str:
    """Recover the current table identifier from a structured prompt body."""
    line = _between(user, "Table:", "\n")
    return line.strip()


def _recover_understandings(user: str) -> dict:
    """Infer which demo tables were referenced in a dry-run prompt."""
    out = {}
    for t in (
        "energy_smart_meter.raw_external_smart_meter",
        "energy_smart_meter.silver_smart_meter_half_hourly_clean",
        "energy_smart_meter.gold_peak_demand_substation_day",
    ):
        if t in user:
            out[t] = {}
    return out


def _recover_executed(user: str) -> list[dict]:
    """Infer a minimal executed-query payload for dry-run interpretation."""
    rows = []
    for cat in ("freshness", "row_count"):
        if cat in user:
            rows.append({"category": cat, "check_name": f"chk_{cat}", "target_table": "smart_meter"})
    return rows or [{"category": "freshness", "check_name": "chk", "target_table": "smart_meter"}]
