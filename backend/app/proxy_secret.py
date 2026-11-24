"""Only accept requests that come through our own proxy (the Cloudflare Worker), which knows PROXY_SECRET.

A host like Render gives the backend a public address of its own. Without this, anyone could call it directly and
pretend to be any IP address, which would defeat the login and signup rate limits.
"""
from __future__ import annotations

import hmac
import json

OPEN_PATHS = {"/api/health"}  # the host's own health check


class ProxySecret:
    def __init__(self, app, secret: str):
        self.app = app
        self.secret = secret.encode()

    def __call__(self, environ, start_response):
        given = environ.pop("HTTP_X_PROXY_SECRET", "")
        client = environ.pop("HTTP_X_CLIENT_IP", "")
        # WSGI header values are latin-1 text; compare_digest needs bytes for anything outside ASCII.
        if hmac.compare_digest(given.encode("latin-1"), self.secret):
            if client:
                environ["REMOTE_ADDR"] = client
        elif environ.get("PATH_INFO") not in OPEN_PATHS:
            body = json.dumps({"error": {"code": "forbidden", "message": "Forbidden."}}).encode()
            start_response("403 FORBIDDEN", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
            return [body]
        return self.app(environ, start_response)
