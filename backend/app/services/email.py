"""Outgoing email behind a small sender interface.

EMAIL_PROVIDER=console (default) writes emails to the backend log, so links can be tested locally
without a provider. EMAIL_PROVIDER=gmail sends through a Gmail account (GOOGLE_EMAIL + an App
Password); EMAIL_PROVIDER=smtp through any SMTP service (SMTP_* + EMAIL_FROM). EMAIL_PROVIDER=resend
sends through Resend's HTTP API once a domain is verified (RESEND_API_KEY + EMAIL_FROM on that domain).

Sending never raises: callers get False and the app carries on (a reset request must answer the
same way whether or not the email went out).
"""
from __future__ import annotations

import smtplib
import socket
import ssl
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
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
        # Warning level: Flask only shows INFO in debug mode, and this is how developers get the link.
        current_app.logger.warning(
            "Email NOT sent (EMAIL_PROVIDER=console) to %s: %s\n%s", email.to, email.subject, email.text
        )
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


class SmtpSender:
    """SMTP with STARTTLS (port 587) or implicit TLS (port 465). One retry on connection problems only:
    an authentication or recipient error won't fix itself, and retrying after the server accepted the
    message could send it twice."""

    def __init__(self, host: str, port: int, username: str, password: str, sender: str, timeout: int = 15):
        self.host, self.port, self.username, self.password = host, port, username, password
        self.sender = sender
        self.timeout = timeout

    def _message(self, email: Email) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg["Message-ID"] = make_msgid(domain=self.username.split("@")[-1] or None)
        msg.set_content(email.text)
        msg.add_alternative(email.html, subtype="html")
        return msg

    def _deliver(self, msg: EmailMessage) -> None:
        context = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context) as smtp:
                smtp.login(self.username, self.password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                smtp.starttls(context=context)
                smtp.login(self.username, self.password)
                smtp.send_message(msg)

    def send(self, email: Email, idempotency_key: str) -> bool:
        msg = self._message(email)
        for attempt in (1, 2):
            try:
                self._deliver(msg)
                return True
            except smtplib.SMTPAuthenticationError:
                status = "authentication failed (check the address and App Password)"
                break
            except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, socket.timeout, OSError) as e:
                status = type(e).__name__
                if attempt == 1:
                    time.sleep(RETRY_DELAY_SECONDS)
            except smtplib.SMTPException as e:
                status = type(e).__name__
                break
        # Log the failure, never the email body (it contains a live link) or the password.
        current_app.logger.warning("Email to %s failed: %s", email.to, status)
        return False


GMAIL_HOST, GMAIL_PORT = "smtp.gmail.com", 587


def get_sender() -> Sender:
    cfg = current_app.config
    if cfg["EMAIL_PROVIDER"] == "gmail":
        address, password = cfg["GOOGLE_EMAIL"], cfg["GOOGLE_APP_PASSWORD"].replace(" ", "")
        if not address or not password:
            current_app.logger.warning("EMAIL_PROVIDER=gmail but GOOGLE_EMAIL or GOOGLE_APP_PASSWORD is missing; using console.")
            return ConsoleSender()
        # Gmail rewrites any other From address to the account's own, so always send as the account.
        sender = formataddr((cfg["GOOGLE_APP_NAME"] or "Business Project Assistance", address))
        return SmtpSender(GMAIL_HOST, GMAIL_PORT, address, password, sender)
    if cfg["EMAIL_PROVIDER"] == "smtp":
        if not cfg["SMTP_HOST"] or not cfg["EMAIL_FROM"]:
            current_app.logger.warning("EMAIL_PROVIDER=smtp but SMTP_HOST or EMAIL_FROM is missing; using console.")
            return ConsoleSender()
        return SmtpSender(cfg["SMTP_HOST"], cfg["SMTP_PORT"], cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"], cfg["EMAIL_FROM"])
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
