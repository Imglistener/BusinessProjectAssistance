import re
from datetime import timedelta

import pytest
import requests

from app.extensions import db
from app.models import AuditLog, PasswordResetToken, User
from app.services import email as email_svc
from app.services.email import Email, ResendSender

from .helpers import register
from .test_members import invite
from .test_projects import make_org


def outbox(app):
    return app.extensions.get("email_outbox", [])


def request_reset(client, email="alex@example.com"):
    return client.post("/api/auth/password-reset", json={"email": email})


def link_token(app):
    return re.search(r"/reset-password/([\w-]+)", outbox(app)[-1].text).group(1)


def confirm(client, token, password="new-password-1"):
    return client.post("/api/auth/password-reset/confirm", json={"token": token, "password": password})


def login(client, password, email="alex@example.com"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ---------- request ----------


def test_reset_flow_changes_password(client, app):
    register(client)
    r = request_reset(client, "Alex@Example.com")
    assert r.status_code == 200
    mail = outbox(app)[-1]
    assert mail.to == "alex@example.com" and "http://localhost:5173/reset-password/" in mail.text
    assert "reset-password/" in mail.html

    token = link_token(app)
    assert PasswordResetToken.query.one().token_hash != token  # only the hash is stored
    assert confirm(client, token).status_code == 200
    assert login(client, "correct-horse").status_code == 401
    assert login(client, "new-password-1").status_code == 200
    assert AuditLog.query.filter_by(action="user.password_reset").count() == 1


def test_same_answer_for_unknown_email(client, app):
    register(client)
    known = request_reset(client).get_json()
    unknown = request_reset(client, "nobody@example.com").get_json()
    assert known == unknown
    assert len(outbox(app)) == 1


def test_link_is_single_use_and_replaced_by_newer_one(client, app):
    register(client)
    request_reset(client)
    first = link_token(app)
    request_reset(client)
    second = link_token(app)
    assert confirm(client, first).get_json()["error"]["code"] == "reset_link_invalid"
    assert confirm(client, second).status_code == 200
    assert confirm(client, second, "another-pass-2").status_code == 400


def test_expired_link(client, app):
    register(client)
    request_reset(client)
    row = PasswordResetToken.query.one()
    row.expires_at = row.created_at - timedelta(seconds=1)
    db.session.commit()
    assert confirm(client, link_token(app)).status_code == 400


def test_requests_are_limited_per_hour(client, app):
    register(client)
    for _ in range(5):
        assert request_reset(client).status_code == 200
    assert len(outbox(app)) == 3


def test_confirm_validation(client, app):
    register(client)
    request_reset(client)
    token = link_token(app)
    r = confirm(client, token, "short")
    assert r.status_code == 400 and r.get_json()["error"]["details"] == {"field": "password"}
    assert confirm(client, "garbage").status_code == 400
    assert client.post("/api/auth/password-reset/confirm", json={"password": "long-enough-1"}).status_code == 400
    assert confirm(client, token).status_code == 200  # the failed attempts didn't use it up


def test_disabled_account_gets_no_email(client, app):
    register(client)
    User.query.one().status = "disabled"
    db.session.commit()
    request_reset(client)
    assert outbox(app) == []


# ---------- invites ----------


def test_invite_is_emailed_in_console_mode_but_not_reported_as_sent(client, app):
    owner, org_id = make_org(client)
    r = invite(client, owner, org_id, email="new@example.com", role="viewer")
    assert r.get_json()["emailed"] is False
    mail = outbox(app)[-1]
    assert mail.to == "new@example.com" and "Acme" in mail.subject and "/invite/" in mail.text


# ---------- Resend sender ----------


class FakeHttp:
    def __init__(self, status):
        self.status_code = status


def mail():
    return Email(to="a@b.co", subject="s", text="t", html="<p>t</p>")


def test_resend_request_shape(monkeypatch, app):
    sent = {}

    def post(url, json, headers, timeout):
        sent.update(url=url, body=json, headers=headers)
        return FakeHttp(200)

    monkeypatch.setattr(requests, "post", post)
    assert ResendSender("re_key", "App <no-reply@mail.example.com>").send(mail(), "password-reset/7") is True
    assert sent["url"] == "https://api.resend.com/emails"
    assert sent["headers"] == {"Authorization": "Bearer re_key", "Idempotency-Key": "password-reset/7"}
    assert sent["body"]["from"] == "App <no-reply@mail.example.com>" and sent["body"]["to"] == ["a@b.co"]


@pytest.mark.parametrize("statuses,expected,calls", [([500, 200], True, 2), ([429, 429], False, 2), ([403], False, 1)])
def test_resend_retries_only_transient_failures(monkeypatch, app, statuses, expected, calls):
    seen = []

    def post(*a, **k):
        seen.append(1)
        return FakeHttp(statuses[len(seen) - 1])

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(email_svc, "RETRY_DELAY_SECONDS", 0)
    assert ResendSender("k", "f").send(mail(), "x") is expected
    assert len(seen) == calls


def test_resend_mode_without_key_falls_back_to_console(app):
    app.config.update(EMAIL_PROVIDER="resend", RESEND_API_KEY="", EMAIL_FROM="")
    assert isinstance(email_svc.get_sender(), email_svc.ConsoleSender)
    app.config.update(RESEND_API_KEY="k", EMAIL_FROM="App <a@b.co>")
    assert isinstance(email_svc.get_sender(), ResendSender)
