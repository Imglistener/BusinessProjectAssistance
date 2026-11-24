"""Running behind the Cloudflare Worker, on a host without a persistent disk."""
import io

from app import create_app
from app.config import TestConfig, database_url
from app.extensions import db
from app.models import StoredFile
from app.services import email as mail

from .helpers import auth_headers
from .test_projects import create_project, make_org


class BehindWorker(TestConfig):
    PROXY_SECRET = "a-long-shared-secret"


def test_only_the_worker_is_served():
    app = create_app(BehindWorker)

    @app.get("/api/whoami")
    def whoami():
        from flask import request

        return {"ip": request.remote_addr, "leaked": request.headers.get("X-Proxy-Secret")}

    client = app.test_client()
    good = {"X-Proxy-Secret": "a-long-shared-secret", "X-Client-IP": "203.0.113.9"}
    assert client.get("/api/whoami", headers=good).get_json() == {"ip": "203.0.113.9", "leaked": None}
    for bad in ({}, {"X-Proxy-Secret": "wrong", "X-Client-IP": "203.0.113.9"}, {"X-Proxy-Secret": "\xe9"}):
        r = client.get("/api/whoami", headers=bad)
        assert r.status_code == 403 and r.get_json()["error"]["code"] == "forbidden"
    assert client.get("/api/health").status_code == 200  # the host's health check


def test_without_a_secret_the_client_ip_header_means_nothing(app):
    with app.test_client() as client:
        client.get("/api/health", headers={"X-Client-IP": "203.0.113.9"})
        from flask import request

        assert request.remote_addr != "203.0.113.9"


def test_receipts_in_the_database(client, app):
    app.config["UPLOAD_STORAGE"] = "database"
    h, org_id = make_org(client)
    pid = create_project(client, h, org_id).get_json()["project"]["id"]
    r = client.post(f"/api/projects/{pid}/expenses", headers=h,
                    json={"amount": "10.00", "expense_date": "2026-11-01", "category": "Other", "description": "Taxi"})
    expense_id = r.get_json()["expense"]["id"]
    pdf = b"%PDF-1.4\n%%EOF\n"

    def upload(data):
        return client.post(f"/api/expenses/{expense_id}/attachments", headers=h,
                           data={"file": (io.BytesIO(data), "r.pdf")}, content_type="multipart/form-data")

    first = upload(pdf).get_json()["attachment"]["id"]
    assert StoredFile.query.count() == 1
    assert client.get(f"/api/attachments/{first}/file", headers=h).data == pdf
    assert client.get(f"/api/attachments/{first}/file", headers=auth_headers(client, "x@example.com")).status_code == 404
    assert client.delete(f"/api/attachments/{first}", headers=h).status_code == 200
    db.session.expire_all()
    assert StoredFile.query.count() == 0

    second = upload(pdf).get_json()["attachment"]["id"]
    StoredFile.query.delete()
    db.session.commit()
    assert client.get(f"/api/attachments/{second}/file", headers=h).status_code == 410


def test_without_email_no_link_reaches_the_logs(app, caplog):
    with app.app_context():
        app.config["EMAIL_PROVIDER"] = "none"
        message = mail.Email(to="a@example.com", subject="Reset", text="https://x/reset-password/secret-token", html="")
        assert mail.send_email(message, "key") is False
    assert "Reset" in caplog.text and "secret-token" not in caplog.text


def test_database_addresses_from_hosts_name_our_driver():
    ours = "postgresql+psycopg2://u:p@ep-x.neon.tech/db?sslmode=require"
    assert database_url("postgresql://u:p@ep-x.neon.tech/db?sslmode=require") == ours
    assert database_url("postgres://u:p@ep-x.neon.tech/db?sslmode=require") == ours
    assert database_url(ours) == ours and database_url("sqlite://") == "sqlite://"
