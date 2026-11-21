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
    """The provider's own usage limit (requests or tokens per minute, or per day) was hit."""

    def __init__(self, message: str, daily: bool = False):
        super().__init__(message)
        self.daily = daily


# Per-minute limits: wait for the provider's retry delay if it's this short (Gemini free tier asks for 20-60s);
# longer waits fail fast with a clear message. One question makes several calls, so the waits of one
# provider object are capped in total too.
MAX_RETRY_WAIT_SECONDS = 60
MAX_TOTAL_WAIT_SECONDS = 90
# Server errors (500/502/503/504: "model overloaded"), timeouts and dropped connections are often momentary.
TRANSIENT_STATUSES = {500, 502, 503, 504}
TRANSIENT_RETRY_DELAY_SECONDS = 2
MAX_ATTEMPTS = 3


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
        self.waited = 0.0  # seconds spent waiting on retries, across this question's calls

    def _sleep(self, seconds: float) -> bool:
        """Wait before a retry if the question's wait budget allows it."""
        if self.waited + seconds > MAX_TOTAL_WAIT_SECONDS:
            return False
        self.waited += seconds
        time.sleep(seconds)
        return True

    def _body(self, messages: list[dict], tools: Optional[list[dict]]) -> dict:
        body: dict = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return body

    def chat(self, messages: list[dict], tools: Optional[list[dict]]) -> ProviderResponse:
        body = self._body(messages, tools)
        transient_retried = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            last = attempt == MAX_ATTEMPTS
            try:
                r = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
            except (requests.Timeout, requests.ConnectionError) as e:
                if last or transient_retried or not self._sleep(TRANSIENT_RETRY_DELAY_SECONDS):
                    raise ProviderError(f"request failed: {type(e).__name__}") from e
                transient_retried = True
                continue
            except requests.RequestException as e:
                raise ProviderError(f"request failed: {type(e).__name__}") from e
            if r.status_code == 429:
                if _is_daily_quota(r):
                    raise ProviderRateLimited("provider daily quota used up (HTTP 429)", daily=True)
                wait = _retry_after(r)
                if last or wait is None or wait > MAX_RETRY_WAIT_SECONDS or not self._sleep(wait + 0.5):
                    raise ProviderRateLimited("provider returned HTTP 429")
                continue
            if r.status_code in TRANSIENT_STATUSES and not (last or transient_retried):
                if self._sleep(TRANSIENT_RETRY_DELAY_SECONDS):
                    transient_retried = True
                    continue
            break
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


def _error_details(r) -> list:
    """Google-style error details ([{"error": {...}}] or {"error": {...}}); [] for anything else."""
    try:
        data = r.json()
    except ValueError:
        return []
    if isinstance(data, list):
        data = data[0] if data else {}
    error = data.get("error") if isinstance(data, dict) else None
    details = error.get("details") if isinstance(error, dict) else None
    return [d for d in details if isinstance(d, dict)] if isinstance(details, list) else []


def _retry_after(r) -> Optional[float]:
    """Seconds to wait: the Retry-After header (Groq), else Gemini's RetryInfo ("24s") in the error body."""
    try:
        return float((getattr(r, "headers", None) or {}).get("retry-after"))
    except (TypeError, ValueError):
        pass
    for d in _error_details(r):
        delay = d.get("retryDelay")
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                pass
    return None


def _is_daily_quota(r) -> bool:
    """Gemini names the quota that ran out; a per-day one won't come back by waiting a minute."""
    for d in _error_details(r):
        for v in d.get("violations") or []:
            if isinstance(v, dict) and "perday" in str(v.get("quotaId", "")).lower():
                return True
    return False


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
