"""LLM provider abstraction. Messages and tool definitions use the OpenAI chat format,
which Groq accepts as-is; other providers get an adapter that translates to and from it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

import requests
from flask import current_app


class ProviderError(Exception):
    """The provider failed, timed out or answered with something we can't use."""


class ProviderRateLimited(ProviderError):
    """The provider's own usage limit (requests or tokens per minute) was hit."""


# Wait for the provider's Retry-After once, if it's this short; longer waits fail fast with a clear message.
MAX_RETRY_WAIT_SECONDS = 10


class ProviderNotConfigured(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text from the model; parsed and validated by the tool layer


@dataclass
class ProviderResponse:
    content: Optional[str]
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class AIProvider(Protocol):
    name: str
    model: str

    def chat(self, messages: list[dict], tools: Optional[list[dict]]) -> ProviderResponse: ...


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: Optional[list[dict]]) -> ProviderResponse:
        body: dict = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        for attempt in (1, 2):
            try:
                r = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                raise ProviderError(f"request failed: {type(e).__name__}") from e
            if r.status_code != 429:
                break
            wait = _retry_after(r)
            if attempt == 2 or wait is None or wait > MAX_RETRY_WAIT_SECONDS:
                raise ProviderRateLimited("provider returned HTTP 429")
            time.sleep(wait)
        if r.status_code != 200:
            # Status only: provider error bodies can echo the prompt back.
            raise ProviderError(f"provider returned HTTP {r.status_code}")
        try:
            data = r.json()
            message = data["choices"][0]["message"]
            calls = [
                ToolCall(id=c["id"], name=c["function"]["name"], arguments=c["function"].get("arguments") or "{}")
                for c in message.get("tool_calls") or []
            ]
            usage = data.get("usage") or {}
            return ProviderResponse(
                content=message.get("content"),
                tool_calls=calls,
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            )
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ProviderError("unexpected response shape") from e


def _retry_after(r) -> Optional[float]:
    try:
        return float(r.headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def get_provider() -> AIProvider:
    cfg = current_app.config
    if cfg["AI_PROVIDER"] == "groq":
        if not cfg["GROQ_API_KEY"]:
            raise ProviderNotConfigured()
        return GroqProvider(cfg["GROQ_API_KEY"], cfg["AI_MODEL"], cfg["GROQ_BASE_URL"], cfg["AI_REQUEST_TIMEOUT_SECONDS"])
    raise ProviderNotConfigured()
