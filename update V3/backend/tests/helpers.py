def register(client, email="alex@example.com", password="correct-horse", first="Alex", last="Doe"):
    return client.post(
        "/api/auth/register",
        json={"first_name": first, "last_name": last, "email": email, "password": password},
    )


def auth_headers(client, email="alex@example.com", password="correct-horse"):
    r = register(client, email=email, password=password)
    assert r.status_code == 201, r.get_json()
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}
