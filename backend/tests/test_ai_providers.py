"""Choosing between AI providers, and switching when one runs out."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import requests

from app.extensions import db
from app.models import AIMessage, AIProviderStatus, AIUsage
from app.services import ai_availability, ai_chat, ai_provider
from app.services.ai_provider import GeminiProvider, GroqProvider, ProviderError, ProviderRateLimited, ProviderTooLarge

from .test_ai import FakeHttp, FakeProvider, ask, call, say, setup


@pytest.fixture()
def two(monkeypatch):
    """Both providers configured, Gemini the default. two(gemini=[...], groq=[...]) scripts their responses."""

    def install(gemini=(), groq=()):
        fakes = {"gemini": FakeProvider(*gemini), "groq": FakeProvider(*groq)}
        for name, p in fakes.items():
            p.name, p.model = name, f"{name}-model"
        monkeypatch.setattr(ai_chat, "get_provider", lambda name=None: fakes[name or "gemini"])
        monkeypatch.setattr(ai_provider, "configured_providers", lambda: ["gemini", "groq"])
        return fakes

    return install


def listing(client, h):
    return {p["id"]: p for p in client.get("/api/ai/providers", headers=h).get_json()["providers"]}


def test_the_chosen_provider_answers(client, two):
    h, org_id, _ = setup(client)
    fakes = two(gemini=[say("from gemini")], groq=[say("from groq")])
    r = ask(client, h, org_id, provider="groq").get_json()
    assert (r["answer"], r["provider"], r["switched"]) == ("from groq", "groq", None)
    assert fakes["gemini"].calls == [] and fakes["groq"].has_backup
    assert ask(client, h, org_id).get_json()["provider"] == "gemini"  # no choice: the default
    assert {m.provider for m in AIMessage.query.filter_by(role="assistant")} == {"groq", "gemini"}


def test_exhausted_provider_is_set_aside_and_the_other_takes_over(client, two):
    h, org_id, pid = setup(client)
    # Groq runs out halfway: its half-done tool calls are dropped and Gemini starts from the question.
    fakes = two(
        groq=[call("list_projects"), ProviderRateLimited("429", retry_after=600)],
        gemini=[call("calculate_budget_metrics", project_id=pid), say("done"), say("second")],
    )
    r = ask(client, h, org_id, provider="groq").get_json()
    assert (r["answer"], r["provider"]) == ("done", "gemini")
    assert r["switched"] == {"from": "groq", "reason": "limit"}
    assert [x["tool"] for x in r["tool_trace"]] == ["calculate_budget_metrics"]
    assert [m["role"] for m in fakes["gemini"].calls[0]["messages"]] == ["system", "user"]

    p = listing(client, h)
    assert p["gemini"]["available"] and not p["groq"]["available"] and not p["groq"]["daily"]
    until = datetime.fromisoformat(p["groq"]["available_at"])
    assert timedelta(seconds=580) < until - datetime.now(timezone.utc) <= timedelta(seconds=600)

    # The next question doesn't bother Groq, and still says why Gemini answered.
    r = ask(client, h, org_id, provider="groq").get_json()
    assert r["provider"] == "gemini" and r["switched"] == {"from": "groq", "reason": "limit"}
    assert len(fakes["groq"].calls) == 2 and not fakes["gemini"].has_backup


def test_the_choice_comes_back_when_the_limit_resets(client, two):
    h, org_id, _ = setup(client)
    two(groq=[say("groq again")])
    db.session.add(AIProviderStatus(provider="groq", exhausted_until=datetime.now(timezone.utc) - timedelta(seconds=1), daily=True))
    db.session.commit()
    assert listing(client, h)["groq"]["available"]
    assert ask(client, h, org_id, provider="groq").get_json()["answer"] == "groq again"


def test_a_failing_provider_is_replaced_but_not_set_aside(client, two):
    h, org_id, _ = setup(client)
    two(gemini=[ProviderError("HTTP 503")], groq=[say("ok")])
    r = ask(client, h, org_id).get_json()
    assert r["switched"] == {"from": "gemini", "reason": "error"} and r["provider"] == "groq"
    assert listing(client, h)["gemini"]["available"]


def test_both_exhausted_is_a_clear_error(client, two):
    h, org_id, _ = setup(client)
    fakes = two(gemini=[ProviderRateLimited("429", retry_after=900)], groq=[ProviderRateLimited("429", retry_after=900)])
    r = ask(client, h, org_id)
    err = r.get_json()["error"]
    assert r.status_code == 503 and err["code"] == "ai_busy"
    assert [p["available"] for p in err["details"]["providers"]] == [False, False]
    # Nothing resets soon: the next question fails at once, without calling anyone.
    assert ask(client, h, org_id).status_code == 503
    assert len(fakes["gemini"].calls) == len(fakes["groq"].calls) == 1


def test_the_message_when_both_are_out_says_when_one_is_back(app):
    now = datetime(2026, 11, 24, 13, 0, tzinfo=timezone.utc)  # 17:00 in Dubai
    with app.app_context():
        message = lambda **d: ai_chat._busy_message(now + timedelta(**d), now, "Asia/Dubai")
        assert "in a minute" in message(seconds=90) and "in a minute" in ai_chat._busy_message(None, now, "UTC")
        assert "back at 19:00" in message(hours=2)
        assert "tomorrow" in message(hours=11)
        ai_availability.mark_exhausted("gemini", ProviderRateLimited("429", retry_after=900), now)
        assert ai_availability.back_at(["gemini", "groq"], now) is None
        assert ai_availability.back_at(["gemini"], now) == now + timedelta(seconds=900)


def test_when_both_are_out_the_one_back_soon_is_waited_for(client, two):
    h, org_id, _ = setup(client)
    now = datetime.now(timezone.utc)
    db.session.add(AIProviderStatus(provider="gemini", exhausted_until=now + timedelta(hours=5), daily=True))
    db.session.add(AIProviderStatus(provider="groq", exhausted_until=now + timedelta(seconds=30), daily=False))
    db.session.commit()
    fakes = two(groq=[say("worth the wait")])
    assert ask(client, h, org_id).get_json()["provider"] == "groq"
    assert not fakes["groq"].has_backup  # so it waits as long as it takes


def test_a_draft_already_made_is_shown_rather_than_redone(client, two):
    h, org_id, _ = setup(client)
    fakes = two(
        gemini=[call("propose_stock_changes", changes=[{"kind": "receive", "item": "Paper", "quantity": 3}]),
                ProviderRateLimited("429", retry_after=60)],
        groq=[say("unused")],
    )
    r = ask(client, h, org_id).get_json()
    assert len(r["stock_proposals"]) == 1 and r["provider"] == "gemini" and fakes["groq"].calls == []
    assert not listing(client, h)["gemini"]["available"]


def test_a_switched_question_counts_once_against_the_personal_limit(client, two, app):
    app.config["AI_REQUESTS_PER_MINUTE"] = 2
    h, org_id, _ = setup(client)
    two(gemini=[ProviderError("down"), ProviderError("down")], groq=[say("1"), say("2")])
    assert ask(client, h, org_id).status_code == 200
    assert ask(client, h, org_id).status_code == 200
    assert ask(client, h, org_id).get_json()["error"]["code"] == "rate_limited"
    assert sorted(u.status for u in AIUsage.query.all()) == ["ok", "ok", "switched_error", "switched_error"]


def test_unknown_provider_is_refused(client, two):
    h, org_id, _ = setup(client)
    two()
    for bad in ("claude", 3, ["groq"]):
        r = ask(client, h, org_id, provider=bad)
        assert r.status_code == 400 and r.get_json()["error"]["details"] == {"field": "provider"}


def test_too_long_for_one_provider_goes_to_the_other(client, two):
    h, org_id, _ = setup(client)
    two(groq=[ProviderTooLarge("413")], gemini=[say("fits"), ProviderTooLarge("413")])
    r = ask(client, h, org_id, provider="groq").get_json()
    assert r["provider"] == "gemini" and listing(client, h)["groq"]["available"]


def test_provider_list_needs_a_login_and_shows_only_configured_ones(client, app):
    assert client.get("/api/ai/providers").status_code == 401
    h, _, _ = setup(client)
    assert listing(client, h) == {}
    app.config.update(GROQ_API_KEY="k", AI_PROVIDER="gemini", AI_MODEL="gemini-x")
    assert listing(client, h)["groq"]["model"] == "openai/gpt-oss-120b"  # AI_MODEL is the default provider's
    app.config.update(GEMINI_API_KEY="g", GROQ_MODEL="groq-y")
    p = listing(client, h)
    assert list(p) == ["gemini", "groq"] and (p["gemini"]["model"], p["groq"]["model"]) == ("gemini-x", "groq-y")


def test_prices_can_differ_per_provider(app):
    with app.app_context():
        app.config.update(GROQ_INPUT_PRICE_PER_MTOK_USD="2", AI_INPUT_PRICE_PER_MTOK_USD=Decimal("1"))
        assert ai_chat._cost("groq", 1_000_000, 0) == 2 and ai_chat._cost("gemini", 1_000_000, 0) == 1


# ---------- resets and patience ----------


def test_gemini_daily_limit_resets_at_midnight_pacific(app):
    with app.app_context():
        now = datetime(2026, 11, 24, 13, 0, tzinfo=timezone.utc)
        ai_availability.mark_exhausted("gemini", ProviderRateLimited("429", daily=True, retry_after=20), now)
        until = db.session.get(AIProviderStatus, "gemini").exhausted_until
        assert until.replace(tzinfo=timezone.utc) == datetime(2026, 11, 25, 8, 0, tzinfo=timezone.utc)


class Http(FakeHttp):
    def __init__(self, status, payload, headers=None):
        super().__init__(status, payload)
        self.headers = headers or {}


def test_groq_daily_limit_is_recognised(monkeypatch):
    body = {"error": {"message": "Rate limit reached for model `x` on tokens per day (TPD): Limit 200000, Used 199000."}}
    monkeypatch.setattr(requests, "post", lambda *a, **k: Http(429, body, {"retry-after": "431"}))
    with pytest.raises(ProviderRateLimited) as e:
        GroqProvider("k", "m", "https://x", 5).chat([], None)
    assert e.value.daily and e.value.retry_after == 431


@pytest.mark.parametrize("wait,slept", [("15", [15.5]), ("40", [])])
def test_with_a_backup_only_short_waits_are_worth_it(monkeypatch, wait, slept):
    waits = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: Http(429, {}, {"retry-after": wait}))
    monkeypatch.setattr(ai_provider.time, "sleep", waits.append)
    p = GeminiProvider("k", "m", "https://x", 5)
    p.has_backup = True
    with pytest.raises(ProviderRateLimited):
        p.chat([], None)
    assert waits == slept


def test_request_too_large(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: Http(413, {}))
    with pytest.raises(ProviderTooLarge):
        GroqProvider("k", "m", "https://x", 5).chat([], None)
