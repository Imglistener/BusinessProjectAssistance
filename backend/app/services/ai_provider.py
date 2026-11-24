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

    def __init__(self, message: str, daily: bool = False, retry_after: Optional[float] = None):
        super().__init__(message)
        self.daily = daily
        self.retry_after = retry_after  # seconds, when the provider said


class ProviderTooLarge(ProviderError):
    """The question with its history and data is more than the provider takes in one request (or one minute)."""


# Per-minute limits: wait for the provider's retry delay if it's this short (Gemini free tier asks for 20-60s);
# longer waits fail fast with a clear message. One question makes several calls, so the waits of one
# provider object are capped in total too.
MAX_RETRY_WAIT_SECONDS = 60
MAX_TOTAL_WAIT_SECONDS = 90
# Server errors (503 "model overloaded" above all) and dropped connections are often momentary: retried with
# growing delays. A timeout has already cost AI_REQUEST_TIMEOUT_SECONDS, so it gets one retry.
TRANSIENT_STATUSES = {500, 502, 503, 504}
TRANSIENT_DELAYS_SECONDS = (2, 5, 10)
MAX_RATE_LIMIT_WAITS = 2
# When another provider can take over, only short pauses are worth it: a longer wait switches instead.
SWITCH_WAIT_SECONDS = 20
SWITCH_TOTAL_WAIT_SECONDS = 25


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
        self.has_backup = False  # another provider can take over, so give up sooner

    def _sleep(self, seconds: float) -> bool:
        """Wait before a retry if the question's wait budget allows it."""
        if self.waited + seconds > (SWITCH_TOTAL_WAIT_SECONDS if self.has_backup else MAX_TOTAL_WAIT_SECONDS):
            return False
        self.waited += seconds
        time.sleep(seconds)
        return True

    def _transient_wait(self, retries_so_far: int) -> bool:
        if retries_so_far >= (1 if self.has_backup else len(TRANSIENT_DELAYS_SECONDS)):
            return False
        return self._sleep(TRANSIENT_DELAYS_SECONDS[retries_so_far])

    def _body(self, messages: list[dict], tools: Optional[list[dict]]) -> dict:
        body: dict = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        return body

    def chat(self, messages: list[dict], tools: Optional[list[dict]]) -> ProviderResponse:
        body = self._body(messages, tools)
        transient = timeouts = limited = 0
        while True:
            try:
                r = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
            except requests.Timeout as e:  # before ConnectionError: a connect timeout is both
                timeouts += 1
                if timeouts > 1 or self.has_backup or not self._sleep(TRANSIENT_DELAYS_SECONDS[0]):
                    raise ProviderError(f"request failed: {type(e).__name__}") from e
                continue
            except requests.ConnectionError as e:
                if not self._transient_wait(transient):
                    raise ProviderError(f"request failed: {type(e).__name__}") from e
                transient += 1
                continue
            except requests.RequestException as e:
                raise ProviderError(f"request failed: {type(e).__name__}") from e
            if r.status_code == 429:
                wait = _retry_after(r)
                if _is_daily_quota(r):
                    raise ProviderRateLimited("provider daily quota used up (HTTP 429)", daily=True, retry_after=wait)
                limited += 1
                if (
                    wait is None
                    or limited > MAX_RATE_LIMIT_WAITS
                    or wait > (SWITCH_WAIT_SECONDS if self.has_backup else MAX_RETRY_WAIT_SECONDS)
                    or not self._sleep(wait + 0.5)
                ):
                    raise ProviderRateLimited("provider returned HTTP 429", retry_after=wait)
                continue
            if r.status_code in TRANSIENT_STATUSES and self._transient_wait(transient):
                transient += 1
                continue
            break
        if r.status_code == 413:
            raise ProviderTooLarge("provider returned HTTP 413")
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
    """The provider names the quota that ran out; a per-day one won't come back by waiting a minute."""
    for d in _error_details(r):
        for v in d.get("violations") or []:
            if isinstance(v, dict) and "perday" in str(v.get("quotaId", "")).lower():
                return True
    # Groq says it in the message: "... on tokens per day (TPD): ...".
    try:
        message = r.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return False
    return isinstance(message, str) and " per day" in message


LABELS = {"gemini": "Gemini", "groq": "Groq"}
DEFAULT_MODELS = {"gemini": "gemini-3.5-flash-lite", "groq": "openai/gpt-oss-120b"}


def configured_providers() -> list[str]:
    """Providers with a key, the default (AI_PROVIDER) first."""
    cfg = current_app.config
    names = [n for n in LABELS if cfg[f"{n.upper()}_API_KEY"]]
    return sorted(names, key=lambda n: n != cfg["AI_PROVIDER"])


def model_for(name: str) -> str:
    cfg = current_app.config
    return cfg[f"{name.upper()}_MODEL"] or (cfg["AI_MODEL"] if name == cfg["AI_PROVIDER"] else "") or DEFAULT_MODELS[name]


def get_provider(name: Optional[str] = None) -> AIProvider:
    cfg = current_app.config
    name = name or cfg["AI_PROVIDER"]
    timeout = cfg["AI_REQUEST_TIMEOUT_SECONDS"]
    if name == "groq" and cfg["GROQ_API_KEY"]:
        return GroqProvider(cfg["GROQ_API_KEY"], model_for(name), cfg["GROQ_BASE_URL"], timeout)
    if name == "gemini" and cfg["GEMINI_API_KEY"]:
        return GeminiProvider(
            cfg["GEMINI_API_KEY"], model_for(name), cfg["GEMINI_BASE_URL"], timeout, cfg["AI_REASONING_EFFORT"] or "low"
        )
    raise ProviderNotConfigured()
