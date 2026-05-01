# OpenRouter client wrapper using OpenAI-compatible chat completions and model metadata fetch.
"""OpenRouter API wrapper built on the OpenAI-compatible Python SDK."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from openai import OpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class ChatResult:
    """Container for parsed message content and the full raw completion payload."""
    content: str
    raw_response: dict[str, Any]


class OpenRouterClient:
    """Client for OpenRouter chat completions and model metadata retrieval."""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize API client and optional OpenRouter attribution headers."""
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is required")

        default_headers: dict[str, str] = {}
        referer = os.getenv("OPENROUTER_HTTP_REFERER")
        title = os.getenv("OPENROUTER_X_TITLE")
        if referer:
            default_headers["HTTP-Referer"] = referer
        if title:
            default_headers["X-Title"] = title

        self._openai = OpenAI(
            api_key=self.api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers=default_headers or None,
        )

    def chat_json(self, model: str, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> ChatResult:
        """Call chat completions and return first response content plus raw payload."""
        completion = self._openai.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        raw = completion.model_dump()
        choices = raw.get("choices") or []
        if not choices:
            raise ValueError("OpenRouter returned no choices")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("OpenRouter returned empty message content")

        return ChatResult(content=content, raw_response=raw)

    def fetch_models(self) -> dict[str, Any]:
        """Fetch model metadata from OpenRouter Models API for pricing fallback."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        referer = os.getenv("OPENROUTER_HTTP_REFERER") # Helps OpenRouter identify where requests are coming from
        title = os.getenv("OPENROUTER_X_TITLE") # Helps label your traffic in OpenRouter’s systems/logging
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

        with httpx.Client(timeout=20.0) as client:
            response = client.get(f"{OPENROUTER_BASE_URL}/models", headers=headers)
            response.raise_for_status()
            return response.json()


def try_parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON string into a dictionary."""
    return json.loads(text)
