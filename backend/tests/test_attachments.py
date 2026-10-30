import io
import os

from app.extensions import db
from app.models import Attachment, AuditLog, Role

from .test_expenses import post_expense, setup_project
from .test_projects import add_member, make_org

PDF = b"%PDF-1.4\n%fake receipt\n" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"0" * 100


def upload(client, h, eid, data=PDF, name="receipt.pdf"):
    return client.post(
        f"/api/expenses/{eid}/attachments",
        data={"file": (io.BytesIO(data), name)},
        headers=h,
        content_type="multipart/form-data",
    )


def setup(client):
    h, org_id, pid = setup_project(client)
    eid = post_expense(client, h, pid).get_json()["expense"]["id"]
    return h, org_id, pid, eid


def test_upload_list_download_delete(client, app):
    h, _, pid, eid = setup(client)
    r = upload(client, h, eid, name="Facture été.pdf")
    assert r.status_code == 201
    att = r.get_json()["attachment"]
    assert (att["filename"], att["content_type"], att["size"]) == ("Facture été.pdf", "application/pdf", len(PDF))

    listed = client.get(f"/api/expenses/{eid}/attachments", headers=h).get_json()["attachments"]
    assert [a["id"] for a in listed] == [att["id"]]
    expenses = client.get(f"/api/projects/{pid}/expenses", headers=h).get_json()["expenses"]
    assert expenses[0]["attachment_count"] == 1

    d = client.get(f"/api/attachments/{att['id']}/file", headers=h)
    assert d.status_code == 200 and d.data == PDF
    assert d.headers["Content-Disposition"].startswith("attachment;")
    assert "filename*=UTF-8''Facture%20%C3%A9t%C3%A9.pdf" in d.headers["Content-Disposition"]
    assert d.headers["X-Content-Type-Options"] == "nosniff"
    assert d.headers["Cache-Control"] == "private, no-store"

    stored = os.path.join(app.config["UPLOAD_DIR"], Attachment.query.one().stored_name)
    assert os.path.exists(stored)
    assert client.delete(f"/api/attachments/{att['id']}", headers=h).status_code == 200
    assert not os.path.exists(stored) and Attachment.query.count() == 0
    assert [e.action for e in AuditLog.query.filter(AuditLog.action.like("attachment.%"))] == ["attachment.added", "attachment.removed"]


def test_type_is_checked_from_content(client):
    h, _, _, eid = setup(client)
    for data, ctype in ((PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")):
        assert upload(client, h, eid, data, "x.bin").get_json()["attachment"]["content_type"] == ctype
    for data, name in ((b"<html><script>alert(1)</script>", "receipt.pdf"), (b"MZ\x90\x00", "a.exe"), (b"GIF89a", "a.gif")):
        r = upload(client, h, eid, data, name)
        assert r.status_code == 415 and r.get_json()["error"]["code"] == "unsupported_file"


def test_size_limits_and_empty(client, app):
    h, _, _, eid = setup(client)
    app.config["MAX_UPLOAD_MB"] = 1
    big = PDF + b"0" * (1024 * 1024)
    r = upload(client, h, eid, big)
    assert r.status_code == 413 and r.get_json()["error"]["code"] == "file_too_large"
    assert upload(client, h, eid, b"").status_code == 400
    r = client.post(f"/api/expenses/{eid}/attachments", data={}, headers=h, content_type="multipart/form-data")
    assert r.status_code == 400


def test_filenames_are_cleaned(client):
    h, _, _, eid = setup(client)
    assert upload(client, h, eid, name="../../etc/passwd.pdf").get_json()["attachment"]["filename"] == "passwd.pdf"
    assert upload(client, h, eid, name="bad\x00\x07name.pdf").get_json()["attachment"]["filename"] == "badname.pdf"
    assert upload(client, h, eid, name="..").get_json()["attachment"]["filename"] == "receipt.pdf"


def test_clean_filename_handles_windows_paths():
    from app.services.storage import clean_filename

    assert clean_filename(r"C:\Users\x\scan.pdf", ".pdf") == "scan.pdf"
    assert clean_filename(None, ".png") == "receipt.png"


def test_file_limit_per_expense(client):
    h, _, _, eid = setup(client)
    for _ in range(10):
        assert upload(client, h, eid).status_code == 201
    assert upload(client, h, eid).status_code == 409


def test_permissions(client):
    h, org_id, pid, eid = setup(client)
    contributor = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    viewer = add_member(client, org_id, "v@example.com", Role.VIEWER)
    outsider, _ = make_org(client, email="rival@example.com", name="Rival")
    aid = upload(client, h, eid).get_json()["attachment"]["id"]

    # Viewers can see and download; contributors can't change someone else's expense.
    assert client.get(f"/api/attachments/{aid}/file", headers=viewer).status_code == 200
    assert upload(client, viewer, eid).status_code == 403
    assert upload(client, contributor, eid).status_code == 403
    assert client.delete(f"/api/attachments/{aid}", headers=contributor).status_code == 403
    own = post_expense(client, contributor, pid).get_json()["expense"]["id"]
    assert upload(client, contributor, own).status_code == 201
    # Outsiders get 404 for everything.
    assert client.get(f"/api/attachments/{aid}/file", headers=outsider).status_code == 404
    assert client.get(f"/api/expenses/{eid}/attachments", headers=outsider).status_code == 404
    assert upload(client, outsider, eid).status_code == 404
    assert client.get(f"/api/attachments/{aid}/file").status_code == 401


def test_voided_expense_and_archived_project(client):
    h, _, pid, eid = setup(client)
    aid = upload(client, h, eid).get_json()["attachment"]["id"]
    client.post(f"/api/expenses/{eid}/void", headers=h)
    assert upload(client, h, eid).status_code == 409
    assert client.get(f"/api/attachments/{aid}/file", headers=h).status_code == 200  # still viewable
    client.patch(f"/api/projects/{pid}", json={"status": "active"}, headers=h)
    eid2 = post_expense(client, h, pid).get_json()["expense"]["id"]
    client.post(f"/api/projects/{pid}/archive", headers=h)
    assert upload(client, h, eid2).status_code == 409


def test_missing_file_on_disk(client, app):
    h, _, _, eid = setup(client)
    aid = upload(client, h, eid).get_json()["attachment"]["id"]
    os.remove(os.path.join(app.config["UPLOAD_DIR"], db.session.get(Attachment, aid).stored_name))
    assert client.get(f"/api/attachments/{aid}/file", headers=h).status_code == 410
