from app.services.ratelimit import RateLimiter

from .helpers import register


def login(client, password, email="alex@example.com"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_account_locks_after_five_failures_even_for_right_password(client):
    register(client)
    for _ in range(5):
        assert login(client, "wrong-password").status_code == 401
    r = login(client, "correct-horse")
    assert r.status_code == 429
    assert r.get_json()["error"]["code"] == "rate_limited"
    assert 0 < int(r.headers["Retry-After"]) <= 15 * 60
    assert "minutes" in r.get_json()["error"]["message"]


def test_unknown_email_locks_the_same_way(client):
    for _ in range(5):
        login(client, "x", email="ghost@example.com")
    assert login(client, "x", email="ghost@example.com").status_code == 429


def test_success_resets_the_failure_count(client):
    register(client)
    for _ in range(4):
        login(client, "wrong-password")
    assert login(client, "correct-horse").status_code == 200
    for _ in range(4):
        assert login(client, "wrong-password").status_code == 401


def test_lock_is_per_email(client):
    register(client)
    register(client, email="other@example.com")
    for _ in range(5):
        login(client, "wrong")
    assert login(client, "correct-horse", email="other@example.com").status_code == 200


def test_per_ip_limit_on_login_spraying(client):
    for i in range(30):
        login(client, "x", email=f"user{i}@example.com")
    assert login(client, "x", email="fresh@example.com").status_code == 429


def test_signup_limit_per_ip(client):
    for i in range(10):
        assert register(client, email=f"s{i}@example.com").status_code == 201
    assert register(client, email="s10@example.com").status_code == 429


def test_reset_limits_per_ip(client):
    for i in range(10):
        assert client.post("/api/auth/password-reset", json={"email": f"r{i}@example.com"}).status_code == 200
    assert client.post("/api/auth/password-reset", json={"email": "r@example.com"}).status_code == 429
    for _ in range(20):
        client.post("/api/auth/password-reset/confirm", json={"token": "x", "password": "long-enough-1"})
    r = client.post("/api/auth/password-reset/confirm", json={"token": "x", "password": "long-enough-1"})
    assert r.status_code == 429


def test_sliding_window_expires():
    now = [1000.0]
    rl = RateLimiter(clock=lambda: now[0])
    for _ in range(3):
        rl.record("k")
    assert rl.retry_after("k", 3, 60) == 60
    now[0] += 30
    assert rl.retry_after("k", 3, 60) == 30
    now[0] += 31
    assert rl.retry_after("k", 3, 60) is None


def test_login_tokens_last_twelve_hours_by_default(app):
    assert app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds() == 12 * 3600
