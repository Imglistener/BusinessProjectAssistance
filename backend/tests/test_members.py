from datetime import timedelta

from app.extensions import db
from app.models import AuditLog, OrganizationInvitation, OrganizationMember, Role, User

from .helpers import auth_headers
from .test_projects import add_member, make_org


def invite(client, headers, org_id, email="new@example.com", role="contributor"):
    return client.post(f"/api/organizations/{org_id}/invitations", json={"email": email, "role": role}, headers=headers)


def user_id(email):
    return User.query.filter_by(email=email).one().id


def members(client, headers, org_id):
    return client.get(f"/api/organizations/{org_id}/members", headers=headers).get_json()["members"]


# ---------- invitations ----------


def test_invite_and_accept_flow(client):
    owner, org_id = make_org(client)
    r = invite(client, owner, org_id, email="New@Example.com")
    assert r.status_code == 201
    token = r.get_json()["token"]
    assert r.get_json()["invitation"]["email"] == "new@example.com"
    # Only a hash is stored.
    assert OrganizationInvitation.query.one().token_hash != token

    preview = client.get(f"/api/invitations/{token}").get_json()["invitation"]
    assert preview == {
        "organization_name": "Acme", "role": "contributor", "email": "new@example.com",
        "invited_by": "Alex", "state": "pending",
    }

    newcomer = auth_headers(client, email="new@example.com")
    r = client.post(f"/api/invitations/{token}/accept", headers=newcomer)
    assert r.status_code == 200 and r.get_json()["organization"]["role"] == "contributor"
    assert client.get(f"/api/organizations/{org_id}/projects", headers=newcomer).status_code == 200

    again = client.post(f"/api/invitations/{token}/accept", headers=newcomer)
    assert again.status_code == 409 and again.get_json()["error"]["code"] == "invitation_accepted"
    assert {e.action for e in AuditLog.query.all()} >= {"member.invited", "invitation.accepted"}


def test_invite_only_works_for_matching_email(client):
    owner, org_id = make_org(client)
    token = invite(client, owner, org_id).get_json()["token"]
    stranger = auth_headers(client, email="stranger@example.com")
    r = client.post(f"/api/invitations/{token}/accept", headers=stranger)
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "invitation_email_mismatch"
    assert client.get(f"/api/organizations/{org_id}/projects", headers=stranger).status_code == 404


def test_expired_revoked_and_unknown_tokens(client):
    owner, org_id = make_org(client)
    token = invite(client, owner, org_id).get_json()["token"]
    newcomer = auth_headers(client, email="new@example.com")

    inv = OrganizationInvitation.query.one()
    inv.expires_at = inv.created_at - timedelta(seconds=1)
    db.session.commit()
    assert client.get(f"/api/invitations/{token}").get_json()["invitation"]["state"] == "expired"
    assert client.post(f"/api/invitations/{token}/accept", headers=newcomer).get_json()["error"]["code"] == "invitation_expired"

    token2 = invite(client, owner, org_id).get_json()["token"]
    inv2 = OrganizationInvitation.query.filter_by(status="pending").one()
    assert client.post(f"/api/organizations/{org_id}/invitations/{inv2.id}/revoke", headers=owner).status_code == 200
    assert client.post(f"/api/invitations/{token2}/accept", headers=newcomer).get_json()["error"]["code"] == "invitation_revoked"

    assert client.get("/api/invitations/not-a-token").status_code == 404
    assert client.post("/api/invitations/not-a-token/accept", headers=newcomer).status_code == 404


def test_reinvite_replaces_pending_invite(client):
    owner, org_id = make_org(client)
    first = invite(client, owner, org_id, role="viewer").get_json()["token"]
    second = invite(client, owner, org_id, role="project_manager").get_json()["token"]
    pending = client.get(f"/api/organizations/{org_id}/invitations", headers=owner).get_json()["invitations"]
    assert [p["role"] for p in pending] == ["project_manager"]
    newcomer = auth_headers(client, email="new@example.com")
    assert client.post(f"/api/invitations/{first}/accept", headers=newcomer).status_code == 409
    assert client.post(f"/api/invitations/{second}/accept", headers=newcomer).get_json()["organization"]["role"] == "project_manager"


def test_invite_validation(client):
    owner, org_id = make_org(client)
    assert invite(client, owner, org_id, email="nope").status_code == 400
    assert invite(client, owner, org_id, role="system_admin").status_code == 400
    assert invite(client, owner, org_id, role="boss").status_code == 400
    r = invite(client, owner, org_id, email="owner@example.com")
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "already_member"


def test_only_owners_manage_invitations(client):
    owner, org_id = make_org(client)
    pm = add_member(client, org_id, "pm@example.com", Role.PROJECT_MANAGER)
    outsider = auth_headers(client, email="out@example.com")
    assert invite(client, pm, org_id).status_code == 403
    assert client.get(f"/api/organizations/{org_id}/invitations", headers=pm).status_code == 403
    assert invite(client, outsider, org_id).status_code == 404
    inv_id = invite(client, owner, org_id).get_json()["invitation"]["id"]
    assert client.post(f"/api/organizations/{org_id}/invitations/{inv_id}/revoke", headers=pm).status_code == 403
    # An invitation can't be revoked through another organization's URL.
    other, other_org = make_org(client, email="rival@example.com", name="Rival")
    assert client.post(f"/api/organizations/{other_org}/invitations/{inv_id}/revoke", headers=other).status_code == 404


def test_removed_member_can_rejoin_with_new_role(client):
    owner, org_id = make_org(client)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    vid = user_id("v@example.com")
    client.post(f"/api/organizations/{org_id}/members/{vid}/remove", headers=owner)
    token = invite(client, owner, org_id, email="v@example.com", role="contributor").get_json()["token"]
    assert client.post(f"/api/invitations/{token}/accept", headers=viewer).status_code == 200
    m = OrganizationMember.query.filter_by(organization_id=org_id, user_id=vid).one()
    assert (m.status, m.role) == ("active", Role.CONTRIBUTOR)


# ---------- members ----------


def test_owner_sees_emails_others_do_not(client):
    owner, org_id = make_org(client)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    assert all("email" in m for m in members(client, owner, org_id))
    assert all("email" not in m for m in members(client, viewer, org_id))


def test_change_role(client):
    owner, org_id = make_org(client)
    add_member(client, org_id, "v@example.com", Role.VIEWER)
    vid = user_id("v@example.com")
    r = client.patch(f"/api/organizations/{org_id}/members/{vid}", json={"role": "project_manager"}, headers=owner)
    assert r.status_code == 200 and r.get_json()["member"]["role"] == "project_manager"
    entry = AuditLog.query.filter_by(action="member.role_changed").one()
    assert entry.meta == {"user_id": vid, "role": ["viewer", "project_manager"]}
    bad = client.patch(f"/api/organizations/{org_id}/members/{vid}", json={"role": "system_admin"}, headers=owner)
    assert bad.status_code == 400


def test_last_owner_is_protected(client):
    owner, org_id = make_org(client)
    oid = user_id("owner@example.com")
    r = client.patch(f"/api/organizations/{org_id}/members/{oid}", json={"role": "viewer"}, headers=owner)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "last_owner"
    assert client.post(f"/api/organizations/{org_id}/members/{oid}/remove", headers=owner).status_code == 409

    # With a second owner, the first can step down.
    add_member(client, org_id, "co@example.com", Role.OWNER)
    r = client.patch(f"/api/organizations/{org_id}/members/{oid}", json={"role": "viewer"}, headers=owner)
    assert r.status_code == 200


def test_remove_and_leave(client):
    owner, org_id = make_org(client)
    pm = add_member(client, org_id, "pm@example.com", Role.PROJECT_MANAGER)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    pm_id, v_id = user_id("pm@example.com"), user_id("v@example.com")

    # Non-owners can't remove others, but can leave.
    assert client.post(f"/api/organizations/{org_id}/members/{v_id}/remove", headers=pm).status_code == 403
    assert client.post(f"/api/organizations/{org_id}/members/{pm_id}/remove", headers=pm).status_code == 200
    assert client.get(f"/api/organizations/{org_id}", headers=pm).status_code == 404
    assert AuditLog.query.filter_by(action="member.left").count() == 1

    assert client.post(f"/api/organizations/{org_id}/members/{v_id}/remove", headers=owner).status_code == 200
    assert client.get(f"/api/organizations/{org_id}/projects", headers=viewer).status_code == 404
    assert client.post(f"/api/organizations/{org_id}/members/{v_id}/remove", headers=owner).status_code == 404
    assert [m["name"] for m in members(client, owner, org_id)] == ["Alex Doe"]
