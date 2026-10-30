"""Outgoing email behind a small sender interface.

EMAIL_PROVIDER=console (default) writes emails to the backend log, so links can be tested locally
without a provider. EMAIL_PROVIDER=resend sends through Resend's HTTP API; it needs RESEND_API_KEY
(a sending-only key restricted to the verified domain) and EMAIL_FROM on that domain.

Sending never raises: callers get False and the app carries on (a reset request must answer the
same way whether or not the email went out).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from html import escape
from typing import Optional, Protocol

import requests
from flask import current_app

RESEND_URL = "https://api.resend.com/emails"
RETRY_DELAY_SECONDS = 1.0


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str


class Sender(Protocol):
    def send(self, email: Email, idempotency_key: str) -> bool: ...


class ConsoleSender:
    """Development sender: logs the email. Returns False because nothing was delivered."""

    def send(self, email: Email, idempotency_key: str) -> bool:
        current_app.extensions.setdefault("email_outbox", []).append(email)
        current_app.logger.info("Email (not sent, console mode) to %s: %s\n%s", email.to, email.subject, email.text)
        return False


class ResendSender:
    def __init__(self, api_key: str, sender: str, timeout: int = 10):
        self.api_key = api_key
        self.sender = sender
        self.timeout = timeout

    def send(self, email: Email, idempotency_key: str) -> bool:
        body = {"from": self.sender, "to": [email.to], "subject": email.subject, "text": email.text, "html": email.html}
        headers = {"Authorization": f"Bearer {self.api_key}", "Idempotency-Key": idempotency_key}
        # One retry for transient failures; the idempotency key stops a duplicate email if the first try landed.
        for attempt in (1, 2):
            try:
                r = requests.post(RESEND_URL, json=body, headers=headers, timeout=self.timeout)
            except requests.RequestException as e:
                status = type(e).__name__
            else:
                if r.status_code in (200, 201):
                    return True
                status = f"HTTP {r.status_code}"
                if r.status_code not in (429,) and r.status_code < 500:
                    break  # a request problem (bad key, unverified domain): retrying won't help
            if attempt == 1:
                time.sleep(RETRY_DELAY_SECONDS)
        # Log the failure, never the email body (it contains a live link).
        current_app.logger.warning("Email to %s failed: %s", email.to, status)
        return False


def get_sender() -> Sender:
    cfg = current_app.config
    if cfg["EMAIL_PROVIDER"] == "resend":
        if not cfg["RESEND_API_KEY"] or not cfg["EMAIL_FROM"]:
            current_app.logger.warning("EMAIL_PROVIDER=resend but RESEND_API_KEY or EMAIL_FROM is missing; using console.")
            return ConsoleSender()
        return ResendSender(cfg["RESEND_API_KEY"], cfg["EMAIL_FROM"])
    return ConsoleSender()


def send_email(email: Email, idempotency_key: str) -> bool:
    return get_sender().send(email, idempotency_key)


def app_link(path: str) -> str:
    return current_app.config["APP_BASE_URL"].rstrip("/") + path


def _layout(heading: str, paragraphs: list[str], button_label: str, url: str, footer: str) -> str:
    """Minimal, inline-styled HTML that renders in common mail clients. All text is escaped."""
    body = "".join(f'<p style="margin:0 0 16px">{escape(p)}</p>' for p in paragraphs)
    return (
        '<div style="font-family:Arial,sans-serif;color:#14183a;max-width:520px;margin:0 auto;padding:24px">'
        f'<h1 style="font-size:20px;margin:0 0 16px">{escape(heading)}</h1>{body}'
        f'<p style="margin:24px 0"><a href="{escape(url)}" style="background:#2b3ccf;color:#fff;padding:12px 20px;'
        f'border-radius:8px;text-decoration:none;font-weight:bold">{escape(button_label)}</a></p>'
        f'<p style="margin:0 0 16px;font-size:13px;color:#565c80">Or paste this link into your browser:<br>{escape(url)}</p>'
        f'<p style="margin:0;font-size:13px;color:#565c80">{escape(footer)}</p></div>'
    )


def password_reset_email(to: str, first_name: str, url: str, minutes: int) -> Email:
    text = (
        f"Hi {first_name},\n\nSomeone asked to reset the password for your BusinessProjectAssistance account.\n"
        f"Use this link within {minutes} minutes:\n\n{url}\n\n"
        "If you didn't ask for this, ignore this email; your password stays the same."
    )
    html = _layout(
        "Reset your password",
        [f"Hi {first_name},", "Someone asked to reset the password for your BusinessProjectAssistance account."],
        "Choose a new password",
        url,
        f"The link works once and expires in {minutes} minutes. If you didn't ask for this, ignore this email.",
    )
    return Email(to=to, subject="Reset your password", text=text, html=html)


def invitation_email(to: str, inviter: Optional[str], org_name: str, role_label: str, url: str) -> Email:
    who = inviter or "Someone"
    text = (
        f"{who} invited you to join {org_name} on BusinessProjectAssistance as {role_label}.\n\n"
        f"Accept the invite:\n\n{url}\n\nThe link works for {to} only and expires in 7 days."
    )
    html = _layout(
        f"Join {org_name}",
        [f"{who} invited you to join {org_name} on BusinessProjectAssistance as {role_label}."],
        "Accept the invite",
        url,
        f"The link works for {to} only and expires in 7 days.",
    )
    return Email(to=to, subject=f"{who} invited you to {org_name}", text=text, html=html)
