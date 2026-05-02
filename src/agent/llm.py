import json
import os

from anthropic import Anthropic, AnthropicBedrock
from dotenv import load_dotenv

from . import mocks

load_dotenv()

USE_BEDROCK = os.getenv("USE_BEDROCK", "1") == "1"
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "anthropic.claude-sonnet-4-5-20250929-v2:0")
DIRECT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

_client = None


def client():
    global _client
    if _client is None:
        if USE_BEDROCK:
            _client = AnthropicBedrock(aws_region=os.getenv("AWS_REGION", "us-east-1"))
        else:
            _client = Anthropic()
    return _client


def call(system: str, user: str, max_tokens: int = 2048, model: str | None = None) -> str:
    if mocks.is_dry_run():
        return _mock_freeform(system, user)
    m = model or (BEDROCK_MODEL if USE_BEDROCK else DIRECT_MODEL)
    resp = client().messages.create(
        model=m,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _mock_freeform(system: str, user: str) -> str:
    """Used by write_final_report; the only freeform-text consumer."""
    if "QA report in Markdown" in system or "Executive Summary" in system:
        return mocks.mock_final_report({}, [])
    return "Mocked response."


def _mock_structured(system: str, user: str, schema_hint: str) -> dict:
    """Route to the right mock by inspecting the schema hint string."""
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
        # Try to recover table understandings from the user message
        return mocks.mock_generate_checks(_recover_understandings(user))
    if "findings" in text and "severity" in text:
        return mocks.mock_interpret_results(_recover_executed(user))
    return {}


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    if j < 0:
        return text[i + len(start):].strip()
    return text[i + len(start):j].strip()


def _listify(s: str) -> list[str]:
    s = s.strip().strip("[]")
    if not s:
        return []
    return [p.strip().strip("'\"") for p in s.split(",") if p.strip()]


def _extract_table_id(user: str) -> str:
    line = _between(user, "Table:", "\n")
    return line.strip()


def _recover_understandings(user: str) -> dict:
    # Build a minimal understanding stub keyed by table ids found in the prompt
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
    # Return placeholder rows; downstream mock just needs categories
    rows = []
    for cat in ("freshness", "row_count"):
        if cat in user:
            rows.append({"category": cat, "check_name": f"chk_{cat}", "target_table": "smart_meter"})
    return rows or [{"category": "freshness", "check_name": "chk", "target_table": "smart_meter"}]


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        first_newline = raw.find("\n")
        if first_newline != -1:
            raw = raw[first_newline + 1 :]
        if raw.endswith("```"):
            raw = raw[: -3]
    return raw.strip()


def call_structured(system: str, user: str, schema_hint: str, max_tokens: int = 2048) -> dict:
    """Asks Claude to emit JSON matching a schema hint and parses it."""
    if mocks.is_dry_run():
        return _mock_structured(system, user, schema_hint)
    extended_system = (
        f"{system}\n\n"
        f"Respond with valid JSON only matching this shape:\n{schema_hint}\n"
        "No prose. No markdown fences. Just JSON."
    )
    raw = _strip_fence(call(extended_system, user, max_tokens=max_tokens))
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        s = raw.find("{")
        e = raw.rfind("}")
        if s >= 0 and e > s:
            return json.loads(raw[s : e + 1])
        s = raw.find("[")
        e = raw.rfind("]")
        if s >= 0 and e > s:
            return json.loads(raw[s : e + 1])
        raise ValueError(f"Could not parse JSON from model output: {raw[:200]}")
