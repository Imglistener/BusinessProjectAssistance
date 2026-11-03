"""Proof-of-work captcha (ALTCHA, self-hosted) for login and signup.

The browser fetches a signed challenge, spends a second or two of CPU finding the solution, and sends it with
the form. We check the signature, the expiry and the solution, and accept each challenge once. No third party
is involved and nothing about the visitor is stored. CAPTCHA_ENABLED=false turns it off (e.g. for scripts).
"""
from __future__ import annotations

import hashlib
import hmac
import threading
import time

import altcha
from flask import current_app

from ..api.errors import ApiError

ALGORITHM = "PBKDF2/SHA-256"
VALID_FOR_SECONDS = 600
MAX_PAYLOAD_CHARS = 4000
FAILED = "Confirm that you're not a robot, then try again."

# Solved challenges, by nonce, until they expire. One server process (see docs/deployment.md).
_used: dict[str, float] = {}
_lock = threading.Lock()


def enabled() -> bool:
    return bool(current_app.config["CAPTCHA_ENABLED"])


def _secret() -> str:
    """CAPTCHA_HMAC_KEY, or one derived from SECRET_KEY so there's no extra secret to manage."""
    configured = current_app.config.get("CAPTCHA_HMAC_KEY")
    if configured:
        return configured
    return hmac.new(current_app.config["SECRET_KEY"].encode(), b"altcha-captcha", hashlib.sha256).hexdigest()


def new_challenge() -> dict:
    challenge = altcha.create_challenge(
        ALGORITHM,
        current_app.config["CAPTCHA_COST"],
        expires_at=int(time.time()) + VALID_FOR_SECONDS,
        hmac_secret=_secret(),
    )
    return challenge.to_dict()


def _fail() -> ApiError:
    return ApiError("captcha_failed", FAILED, 400, {"field": "captcha"})


def check(payload: object) -> None:
    """Raise unless `payload` solves a challenge we issued, unexpired and not used before."""
    if not enabled():
        return
    if not isinstance(payload, str) or not payload or len(payload) > MAX_PAYLOAD_CHARS:
        raise _fail()
    try:
        result = altcha.verify_solution(payload, _secret())
        nonce = altcha.Payload.from_base64(payload).challenge.parameters.nonce
    except Exception:  # malformed payloads raise various errors
        raise _fail()
    if not result.verified:
        raise _fail()
    now = time.time()
    with _lock:
        for key in [k for k, until in _used.items() if until < now]:
            del _used[key]
        if nonce in _used:
            raise _fail()
        _used[nonce] = now + VALID_FOR_SECONDS


def reset_for_tests() -> None:
    _used.clear()
