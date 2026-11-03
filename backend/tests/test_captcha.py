import time

import altcha
import pytest

from app.services import captcha

from .helpers import register

SIGNUP = {"first_name": "Alex", "last_name": "Doe", "email": "alex@example.com", "password": "correct-horse"}


@pytest.fixture()
def on(app):
    app.config["CAPTCHA_ENABLED"] = True
    captcha.reset_for_tests()
    yield
    captcha.reset_for_tests()


def solved(client) -> str:
    """Fetch a challenge and solve it, like the widget does in the browser."""
    challenge = altcha.Challenge.from_dict(client.get("/api/auth/captcha").get_json())
    return altcha.Payload(challenge, altcha.solve_challenge(challenge)).to_base64()


def test_challenge_is_signed_and_expires(client, on):
    data = client.get("/api/auth/captcha").get_json()
    assert data["signature"] and data["parameters"]["algorithm"] == "PBKDF2/SHA-256"
    assert time.time() < data["parameters"]["expiresAt"] <= time.time() + captcha.VALID_FOR_SECONDS + 1


def test_disabled_means_no_challenge_and_no_check(client):
    assert client.get("/api/auth/captcha").get_json() == {"enabled": False}
    assert register(client).status_code == 201


def test_signup_and_login_need_a_solution(client, on):
    r = client.post("/api/auth/register", json=SIGNUP)
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "captcha_failed"
    assert r.get_json()["error"]["details"]["field"] == "captcha"
    assert client.post("/api/auth/register", json={**SIGNUP, "captcha": solved(client)}).status_code == 201

    login = {"email": SIGNUP["email"], "password": SIGNUP["password"]}
    assert client.post("/api/auth/login", json=login).get_json()["error"]["code"] == "captcha_failed"
    assert client.post("/api/auth/login", json={**login, "captcha": solved(client)}).status_code == 200


def test_a_solution_works_once(client, on):
    register_payload = solved(client)
    assert client.post("/api/auth/register", json={**SIGNUP, "captcha": register_payload}).status_code == 201
    login = {"email": SIGNUP["email"], "password": SIGNUP["password"], "captcha": register_payload}
    assert client.post("/api/auth/login", json=login).get_json()["error"]["code"] == "captcha_failed"


def test_wrong_or_forged_solutions_are_refused(client, on):
    challenge = altcha.Challenge.from_dict(client.get("/api/auth/captcha").get_json())
    right = altcha.solve_challenge(challenge)
    wrong = altcha.Payload(challenge, altcha.Solution(right.counter + 1, right.derived_key)).to_base64()
    # A challenge we didn't sign, solved honestly.
    forged_challenge = altcha.create_challenge("PBKDF2/SHA-256", 50, hmac_secret="not-our-key",
                                               expires_at=int(time.time()) + 60)
    forged = altcha.Payload(forged_challenge, altcha.solve_challenge(forged_challenge)).to_base64()
    login = {"email": "x@example.com", "password": "whatever-123"}
    for bad in (wrong, forged, "not base64 at all", "", 42, "A" * 5000):
        r = client.post("/api/auth/login", json={**login, "captcha": bad})
        assert r.get_json()["error"]["code"] == "captcha_failed", bad


def test_expired_solution_is_refused(client, on, monkeypatch):
    payload = solved(client)
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + captcha.VALID_FOR_SECONDS + 5)
    r = client.post("/api/auth/login", json={"email": "x@example.com", "password": "pw-123456", "captcha": payload})
    assert r.get_json()["error"]["code"] == "captcha_failed"


def test_field_errors_come_before_the_captcha(client, on):
    # A typo in the form doesn't use up the solved captcha.
    payload = solved(client)
    r = client.post("/api/auth/register", json={**SIGNUP, "email": "not-an-email", "captcha": payload})
    assert r.get_json()["error"]["details"]["field"] == "email"
    assert client.post("/api/auth/register", json={**SIGNUP, "captcha": payload}).status_code == 201


def test_message_follows_the_language(client, on):
    r = client.post("/api/auth/login", json={"email": "x@example.com", "password": "pw"},
                    headers={"Accept-Language": "fr"})
    assert "robot" in r.get_json()["error"]["message"] and "Confirmez" in r.get_json()["error"]["message"]
