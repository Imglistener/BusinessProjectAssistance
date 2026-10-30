"""Sliding-window rate limits for sensitive endpoints (login, signup, password reset).

Counts live in memory, per backend process: right for a single-process deployment. Running several
workers or servers needs a shared store (e.g. Redis); see docs/deployment.md.
"""
from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Optional

from flask import current_app, request

from ..errors import ApiError


class RateLimiter:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str, window: float) -> deque:
        hits = self._hits[key]
        cutoff = self._clock() - window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def retry_after(self, key: str, limit: int, window: float) -> Optional[int]:
        """Seconds until another attempt is allowed, or None if one is allowed now."""
        with self._lock:
            hits = self._prune(key, window)
            if len(hits) < limit:
                if not hits:
                    self._hits.pop(key, None)  # don't keep empty keys around
                return None
            return max(1, math.ceil(hits[0] + window - self._clock()))

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(self._clock())

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


def limiter() -> RateLimiter:
    return current_app.extensions.setdefault("rate_limiter", RateLimiter())


def client_ip() -> str:
    # Behind a reverse proxy, set PROXY_FIX_X_FOR so remote_addr is the real client (see create_app).
    return request.remote_addr or "unknown"


def too_many(retry_after: int) -> ApiError:
    minutes = math.ceil(retry_after / 60)
    wait = f"{minutes} minute{'s' if minutes != 1 else ''}" if retry_after >= 60 else "a moment"
    return ApiError("rate_limited", f"Too many attempts. Try again in {wait}.", 429, {"retry_after": retry_after})


def enforce(key: str, limit: int, window: float) -> None:
    """Count this request and refuse it when `key` is over `limit` per `window` seconds."""
    rl = limiter()
    wait = rl.retry_after(key, limit, window)
    if wait is not None:
        raise too_many(wait)
    rl.record(key)
