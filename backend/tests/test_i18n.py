"""Translations: catalog coverage, template matching, and the API answering in the requested language."""
import ast
import pathlib
from datetime import date

import pytest

from app import i18n
from app.api.members import ROLE_LABELS
from app.api.validation import FIELD_LABELS
from app.i18n import human_date, normalize, translate
from app.models import Role, User
from app.services import travel
from app.translations import ar, fr

from .helpers import register
from .test_password_reset import outbox, request_reset
from .test_projects import add_member, make_org

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
FR = {"Accept-Language": "fr"}


# ---------- catalog coverage ----------


def _template(node):
    """An f-string as a catalog key: each {expression} becomes a {name} placeholder."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{x}" for v in node.values)
    return None


def _messages():
    """English texts the API sends to people: ApiError/_bad messages, estimate notes, notifications."""
    found = set()

    def add(node):
        if isinstance(node, ast.IfExp):
            add(node.body)
            add(node.orelse)
            return
        text = _template(node)
        if text and any(c.isalpha() for c in text):
            found.add(text)

    for path in APP.rglob("*.py"):
        if "translations" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", "")
            if name in ("ApiError", "_bad") and len(node.args) >= 2:
                add(node.args[1])
            elif name == "EstimateUnavailable" and node.args:
                add(node.args[0])
            elif name == "notify":
                for kw in node.keywords:
                    if kw.arg in ("title", "body"):
                        add(kw.value)
            elif name == "append" and path.name == "travel.py":
                for a in node.args:
                    add(a)
        if path.name == "travel.py":
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.List):
                    for e in node.elts:
                        add(e)
    return found


def _shape(key: str) -> str:
    """Compare templates by their literal text; placeholder names differ between code and catalog."""
    import re

    return re.sub(r"\{\w+\}", "{x}", key)


@pytest.mark.parametrize("catalog", [fr.MESSAGES, ar.MESSAGES], ids=["fr", "ar"])
def test_every_api_message_has_a_translation(catalog):
    shapes = {_shape(k) for k in catalog}
    missing = sorted(m for m in _messages() if _shape(m) not in shapes)
    assert not missing, missing


@pytest.mark.parametrize("catalog", [fr.MESSAGES, ar.MESSAGES], ids=["fr", "ar"])
def test_labels_shown_inside_messages_are_translated(catalog):
    labels = set(FIELD_LABELS.values()) | set(ROLE_LABELS.values()) | {v.label for v in travel.VEHICLES.values()}
    labels |= {"diesel", "petrol", "road route from the map", "distance entered by hand"}
    assert not sorted(label for label in labels if label not in catalog)


@pytest.mark.parametrize("catalog", [fr.MESSAGES, ar.MESSAGES], ids=["fr", "ar"])
def test_translations_keep_the_placeholders(catalog):
    import re

    for key, value in catalog.items():
        assert sorted(re.findall(r"\{\w+\}", key)) == sorted(re.findall(r"\{\w+\}", value)), key


# ---------- translate() ----------


def test_translate_exact_and_templates():
    assert translate("Expense not found.", "fr") == "Dépense introuvable."
    assert translate("Only 3 pcs on hand.", "fr") == "Seulement 3 pcs en stock."
    # A placeholder value that is itself in the catalog is translated too.
    assert translate("Project name is required.", "fr") == "Nom du projet : champ obligatoire."
    assert translate("In Website. Due 20 Nov 2026.", "fr") == "Dans Website. Échéance le 20 nov. 2026."


def test_arabic_messages_and_dates():
    assert translate("Incorrect email or password.", "ar") == "البريد الإلكتروني أو كلمة المرور غير صحيحة."
    assert translate("Project name is required.", "ar") == "اسم المشروع: حقل مطلوب."
    assert human_date(date(2026, 11, 8), "ar") == "8 نونبر 2026"


def test_translate_leaves_unknown_text_and_english_alone():
    assert translate("Something nobody wrote down.", "fr") == "Something nobody wrote down."
    assert translate("Expense not found.", "en") == "Expense not found."
    assert translate(None, "fr") is None


def test_language_codes_and_dates():
    assert normalize("fr-MA") == "fr" and normalize("AR") == "ar" and normalize("de") == "en" and normalize(None) == "en"
    assert human_date(date(2026, 11, 8), "fr") == "8 nov. 2026"
    assert human_date(date(2026, 11, 8)) == "8 Nov 2026"


def test_underscore_fills_after_translating():
    assert i18n._("Hi {name},", "fr", name="Salma") == "Bonjour Salma,"
    assert i18n._("Hi {name},", "en", name="Salma") == "Hi Salma,"


# ---------- API ----------


def test_errors_follow_accept_language(client):
    register(client)
    r = client.post("/api/auth/login", json={"email": "alex@example.com", "password": "wrong"}, headers=FR)
    assert r.status_code == 401
    assert r.get_json()["error"] == {"code": "invalid_credentials", "message": "E-mail ou mot de passe incorrect."}
    r = client.post("/api/auth/login", json={"email": "alex@example.com", "password": "wrong"}, headers={"Accept-Language": "ar"})
    assert r.get_json()["error"]["message"] == "البريد الإلكتروني أو كلمة المرور غير صحيحة."
    r = client.post("/api/auth/login", json={"email": "alex@example.com", "password": "wrong"})
    assert r.get_json()["error"]["message"] == "Incorrect email or password."


def test_validation_messages_name_the_field_in_the_language(client):
    h, org_id = make_org(client)
    r = client.post(f"/api/organizations/{org_id}/projects", json={"name": ""}, headers={**h, **FR})
    assert r.status_code == 400
    assert r.get_json()["error"]["message"] == "Nom du projet : champ obligatoire."
    assert r.get_json()["error"]["details"] == {"field": "name"}


def test_unknown_routes_and_missing_tokens_are_translated(client):
    assert client.get("/api/nope", headers=FR).get_json()["error"]["message"] == "Ressource introuvable."
    assert client.get("/api/auth/me", headers=FR).get_json()["error"]["message"] == "Authentification requise."


def test_register_saves_the_locale_and_me_can_change_it(client):
    r = client.post(
        "/api/auth/register",
        json={"first_name": "Salma", "last_name": "B", "email": "s@example.com", "password": "correct-horse", "locale": "fr"},
    )
    assert r.get_json()["user"]["locale"] == "fr"
    h = {"Authorization": f"Bearer {r.get_json()['access_token']}"}
    r = client.patch("/api/auth/me", json={"locale": "ar"}, headers=h)
    assert r.status_code == 200 and r.get_json()["user"]["locale"] == "ar"
    assert client.get("/api/auth/me", headers=h).get_json()["user"]["locale"] == "ar"
    r = client.patch("/api/auth/me", json={"locale": "de"}, headers=h)
    assert r.status_code == 400 and r.get_json()["error"]["details"] == {"field": "locale"}


def test_register_without_locale_uses_the_request_language(client):
    r = client.post(
        "/api/auth/register",
        json={"first_name": "A", "last_name": "B", "email": "a@example.com", "password": "correct-horse"},
        headers={"Accept-Language": "fr-MA,fr;q=0.9"},
    )
    assert r.get_json()["user"]["locale"] == "fr"


def test_reset_email_uses_the_account_language(client, app):
    register(client)
    User.query.filter_by(email="alex@example.com").one().locale = "fr"
    from app.extensions import db

    db.session.commit()
    r = client.post("/api/auth/password-reset", json={"email": "alex@example.com"}, headers=FR)
    assert r.get_json()["message"].startswith("Si un compte existe")
    mail = outbox(app)[-1]
    assert mail.subject == "Réinitialisez votre mot de passe"
    assert "Bonjour Alex," in mail.text and "Choisir un nouveau mot de passe" in mail.html


def test_reset_email_stays_english_by_default(client, app):
    register(client)
    request_reset(client)
    assert outbox(app)[-1].subject == "Reset your password"


def test_notifications_are_shown_in_the_reader_language(client):
    h, org_id = make_org(client)
    pid = client.post(f"/api/organizations/{org_id}/projects", json={"name": "Website"}, headers=h).get_json()["project"]["id"]
    c = add_member(client, org_id, "c@example.com", Role.CONTRIBUTOR)
    assignee = User.query.filter_by(email="c@example.com").one().id
    client.post(
        f"/api/projects/{pid}/tasks", json={"title": "Book venue", "assignee_id": assignee, "due_date": "2026-11-20"}, headers=h
    )
    n = client.get("/api/notifications", headers={**c, **FR}).get_json()["notifications"][0]
    assert n["title"] == "Nouvelle tâche pour vous : Book venue"
    assert n["body"] == "Dans Website. Échéance le 20 nov. 2026."
