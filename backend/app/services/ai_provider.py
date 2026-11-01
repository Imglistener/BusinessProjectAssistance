"""LLM provider abstraction. Messages and tool definitions use the OpenAI chat format,
which Groq accepts as-is; Gemini (through its OpenAI-compatible endpoint) gets small adaptations.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

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
    extra: Optional[dict] = None  # provider data to send back unchanged (Gemini's thought signatures)


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


class OpenAICompatibleProvider:
    """Any provider with an OpenAI-style /chat/completions endpoint. Subclasses adapt the request."""

    name = "openai-compatible"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _body(self, messages: list[dict], tools: Optional[list[dict]]) -> dict:
        body: dict = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return body

    def chat(self, messages: list[dict], tools: Optional[list[dict]]) -> ProviderResponse:
        body = self._body(messages, tools)
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
                ToolCall(
                    id=c["id"],
                    name=c["function"]["name"],
                    arguments=c["function"].get("arguments") or "{}",
                    extra=c.get("extra_content"),
                )
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


class GroqProvider(OpenAICompatibleProvider):
    """Groq takes the OpenAI format as-is."""

    name = "groq"


class GeminiProvider(OpenAICompatibleProvider):
    """Google Gemini through its OpenAI-compatible endpoint.

    Adapted here: thinking is kept short (it can't be turned off on Gemini 3 and is billed as output); tool
    schemas use `nullable` instead of a list of types; only the first message may be a system message.
    Tool calls carry `extra_content` (thought signatures) that must be sent back as received: ToolCall.extra
    keeps it and the chat loop returns it with the assistant turn.
    """

    name = "gemini"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int, reasoning_effort: Optional[str] = "low"):
        super().__init__(api_key, model, base_url, timeout)
        self.reasoning_effort = reasoning_effort

    def _body(self, messages: list[dict], tools: Optional[list[dict]]) -> dict:
        messages = [
            {"role": "user", "content": m["content"]} if m.get("role") == "system" and i > 0 else m
            for i, m in enumerate(messages)
        ]
        body = super()._body(messages, [_gemini_tool(t) for t in tools] if tools else None)
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        return body


def _gemini_tool(tool: dict) -> dict:
    fn = tool.get("function") or {}
    if "parameters" not in fn:
        return tool
    return {**tool, "function": {**fn, "parameters": _gemini_schema(fn["parameters"])}}


def _gemini_schema(schema: Any) -> Any:
    """{"type": ["string", "null"]} becomes {"type": "string", "nullable": true}, at any depth."""
    if isinstance(schema, list):
        return [_gemini_schema(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: _gemini_schema(v) for k, v in schema.items()}
    kind = out.get("type")
    if isinstance(kind, list):
        rest = [t for t in kind if t != "null"]
        out["type"] = rest[0] if len(rest) == 1 else rest
        if "null" in kind:
            out["nullable"] = True
    return out


def _retry_after(r) -> Optional[float]:
    try:
        return float(r.headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def get_provider() -> AIProvider:
    cfg = current_app.config
    timeout = cfg["AI_REQUEST_TIMEOUT_SECONDS"]
    if cfg["AI_PROVIDER"] == "groq":
        if not cfg["GROQ_API_KEY"]:
            raise ProviderNotConfigured()
        return GroqProvider(cfg["GROQ_API_KEY"], cfg["AI_MODEL"], cfg["GROQ_BASE_URL"], timeout)
    if cfg["AI_PROVIDER"] == "gemini":
        if not cfg["GEMINI_API_KEY"]:
            raise ProviderNotConfigured()
        return GeminiProvider(
            cfg["GEMINI_API_KEY"], cfg["AI_MODEL"], cfg["GEMINI_BASE_URL"], timeout, cfg["AI_REASONING_EFFORT"] or "low"
        )
    raise ProviderNotConfigured()
