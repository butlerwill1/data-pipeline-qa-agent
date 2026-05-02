import json
import os

from anthropic import Anthropic, AnthropicBedrock
from dotenv import load_dotenv

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
    m = model or (BEDROCK_MODEL if USE_BEDROCK else DIRECT_MODEL)
    resp = client().messages.create(
        model=m,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


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
