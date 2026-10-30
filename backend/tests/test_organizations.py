from app.models import AuditLog, OrganizationMember

from .helpers import auth_headers


def create_org(client, headers, name="Acme"):
    return client.post("/api/organizations", json={"name": name}, headers=headers)


def test_create_org_makes_creator_owner_with_defaults(client):
    h = auth_headers(client)
    r = create_org(client, h)
    assert r.status_code == 201
    org = r.get_json()["organization"]
    assert org["role"] == "owner"
    assert org["default_currency"] == "MAD"


def test_create_org_writes_audit_log(client):
    h = auth_headers(client)
    org_id = create_org(client, h).get_json()["organization"]["id"]
    entry = AuditLog.query.filter_by(organization_id=org_id, action="organization.created").one()
    assert entry.entity_id == org_id and entry.actor_id is not None
    assert OrganizationMember.query.filter_by(organization_id=org_id).count() == 1


def test_create_org_validation_and_auth(client):
    h = auth_headers(client)
    assert client.post("/api/organizations", json={}, headers=h).status_code == 400
    assert client.post("/api/organizations", json={"name": "X", "default_currency": "MADD"}, headers=h).status_code == 400
    assert client.post("/api/organizations", json={"name": "X"}).status_code == 401


def test_list_only_own_organizations(client):
    a = auth_headers(client, email="a@example.com")
    b = auth_headers(client, email="b@example.com")
    create_org(client, a, "A Corp")
    create_org(client, b, "B Corp")
    names = [o["name"] for o in client.get("/api/organizations", headers=a).get_json()["organizations"]]
    assert names == ["A Corp"]


def test_cannot_read_another_organization_by_id(client):
    a = auth_headers(client, email="a@example.com")
    b = auth_headers(client, email="b@example.com")
    org_id = create_org(client, a).get_json()["organization"]["id"]
    assert client.get(f"/api/organizations/{org_id}", headers=a).status_code == 200
    r = client.get(f"/api/organizations/{org_id}", headers=b)
    assert r.status_code == 404  # same as a non-existent id
    assert client.get("/api/organizations/99999", headers=b).status_code == 404


def test_members_list_for_members_only(client):
    from app.models import Role

    from .test_projects import add_member

    owner = auth_headers(client, email="owner@example.com")
    org_id = create_org(client, owner).get_json()["organization"]["id"]
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    outsider = auth_headers(client, email="out@example.com")

    members = client.get(f"/api/organizations/{org_id}/members", headers=viewer).get_json()["members"]
    assert sorted(m["role"] for m in members) == ["owner", "viewer"]
    assert all(set(m) == {"user_id", "name", "role"} for m in members)  # no emails
    assert client.get(f"/api/organizations/{org_id}/members", headers=outsider).status_code == 404
    assert client.get(f"/api/organizations/{org_id}/members").status_code == 401
