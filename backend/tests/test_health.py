def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_unknown_route_returns_clean_error(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == "not_found"
