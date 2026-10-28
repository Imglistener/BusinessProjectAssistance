from app.models import User

from .helpers import auth_headers, register


def test_register_success_hashes_password(client, app):
    r = register(client)
    assert r.status_code == 201
    body = r.get_json()
    assert body["access_token"]
    assert body["user"]["email"] == "alex@example.com"
    assert "password" not in str(body)
    user = User.query.filter_by(email="alex@example.com").first()
    assert user.password_hash != "correct-horse"


def test_register_normalizes_email_and_blocks_duplicates(client):
    assert register(client, email="Alex@Example.com").status_code == 201
    r = register(client, email="alex@example.com")
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "email_taken"


def test_register_validation(client):
    assert register(client, password="short").status_code == 400
    assert register(client, email="not-an-email").status_code == 400
    assert client.post("/api/auth/register", json={}).status_code == 400
    assert client.post("/api/auth/register", data="nope").status_code == 400


def test_login_success_and_failures(client):
    register(client)
    ok = client.post("/api/auth/login", json={"email": "ALEX@example.com", "password": "correct-horse"})
    assert ok.status_code == 200 and ok.get_json()["access_token"]

    wrong = client.post("/api/auth/login", json={"email": "alex@example.com", "password": "bad-password"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "bad-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json() == unknown.get_json()  # no account enumeration


def test_me_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "unauthorized"


def test_me_returns_user(client):
    headers = auth_headers(client)
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.get_json()["user"]["email"] == "alex@example.com"
    assert r.get_json()["memberships"] == []
