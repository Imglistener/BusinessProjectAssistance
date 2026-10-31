import re
from datetime import timedelta

from flask import jsonify
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..i18n import LANGS, normalize, request_lang, translate
from ..models import OrganizationMember, PasswordResetToken, User, utcnow
from ..services.audit import log_action
from ..services.email import app_link, password_reset_email, send_email
from ..services.ratelimit import client_ip, enforce, limiter, too_many
from ..services.tokens import aware, hash_token, new_token
from . import api_bp
from .errors import ApiError
from .validation import get_json_body, require_str

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
RESET_TTL_MINUTES = 30
MAX_RESETS_PER_HOUR = 3
# Sliding windows, in seconds. Failed logins are counted per email (to stop password guessing on one
# account) and all attempts per IP (to stop spraying many accounts).
LOGIN_FAILURES_PER_EMAIL = (5, 15 * 60)
LOGIN_ATTEMPTS_PER_IP = (30, 15 * 60)
SIGNUPS_PER_IP = (10, 60 * 60)
RESET_REQUESTS_PER_IP = (10, 60 * 60)
RESET_CONFIRMS_PER_IP = (20, 60 * 60)
RESET_REQUESTED = "If an account exists for that email, we've sent a link to reset the password."


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "locale": user.locale or "en",
    }


def current_user() -> User:
    """Resolve the authenticated user; call only inside a @jwt_required() view."""
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or user.status != "active":
        raise ApiError("unauthorized", "Account not available.", 401)
    return user


@api_bp.post("/auth/register")
def register():
    enforce(f"signup:ip:{client_ip()}", *SIGNUPS_PER_IP)
    data = get_json_body()
    first_name = require_str(data, "first_name", max_len=100)
    last_name = require_str(data, "last_name", max_len=100)
    email = require_str(data, "email").lower()
    password = require_str(data, "password", max_len=128, min_len=MIN_PASSWORD_LENGTH)

    if not EMAIL_RE.match(email):
        raise ApiError("validation_error", "Invalid email address.", 400, {"field": "email"})
    if User.query.filter_by(email=email).first():
        raise ApiError("email_taken", "An account with this email already exists.", 409)

    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=generate_password_hash(password),
        locale=normalize(data.get("locale") if isinstance(data.get("locale"), str) else request_lang()),
    )
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token, user=user_to_dict(user)), 201


@api_bp.post("/auth/login")
def login():
    enforce(f"login:ip:{client_ip()}", *LOGIN_ATTEMPTS_PER_IP)
    data = get_json_body()
    email = require_str(data, "email").lower()
    password = data.get("password")

    # Checked before the password, so a locked account can't be probed with more guesses.
    # Applies to any email string, so it doesn't reveal which accounts exist.
    failures_key = f"login:fail:{email}"
    wait = limiter().retry_after(failures_key, *LOGIN_FAILURES_PER_EMAIL)
    if wait is not None:
        raise too_many(wait)

    user = User.query.filter_by(email=email).first()
    # One generic error for unknown email and wrong password.
    if (
        user is None
        or user.status != "active"
        or not isinstance(password, str)
        or not check_password_hash(user.password_hash, password)
    ):
        limiter().record(failures_key)
        raise ApiError("invalid_credentials", "Incorrect email or password.", 401)
    limiter().clear(failures_key)

    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token, user=user_to_dict(user))


@api_bp.get("/auth/me")
@jwt_required()
def me():
    user = current_user()
    memberships = OrganizationMember.query.filter_by(user_id=user.id, status="active").all()
    return jsonify(
        user=user_to_dict(user),
        memberships=[
            {"organization_id": m.organization_id, "role": m.role.value} for m in memberships
        ],
    )


@api_bp.patch("/auth/me")
@jwt_required()
def update_me():
    """Only the language for now: emails and notifications follow it."""
    user = current_user()
    data = get_json_body()
    if "locale" in data:
        if data["locale"] not in LANGS:
            raise ApiError("validation_error", "Language must be en, fr or ar.", 400, {"field": "locale"})
        user.locale = data["locale"]
        db.session.commit()
    return jsonify(user=user_to_dict(user))


@api_bp.post("/auth/password-reset")
def request_password_reset():
    """Always the same answer, so the form can't be used to find out who has an account."""
    enforce(f"reset:ip:{client_ip()}", *RESET_REQUESTS_PER_IP)
    data = get_json_body()
    email = require_str(data, "email").lower()
    user = User.query.filter_by(email=email, status="active").first()
    if user is not None:
        recent = PasswordResetToken.query.filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at >= utcnow() - timedelta(hours=1),
        ).count()
        if recent < MAX_RESETS_PER_HOUR:
            # A new link replaces any earlier unused one.
            PasswordResetToken.query.filter_by(user_id=user.id, used_at=None).update({"used_at": utcnow()})
            token = new_token()
            row = PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=utcnow() + timedelta(minutes=RESET_TTL_MINUTES),
            )
            db.session.add(row)
            db.session.commit()
            send_email(
                password_reset_email(
                    user.email,
                    user.first_name,
                    app_link(f"/reset-password/{token}"),
                    RESET_TTL_MINUTES,
                    lang=normalize(user.locale),
                ),
                idempotency_key=f"password-reset/{row.id}",
            )
    return jsonify(ok=True, message=translate(RESET_REQUESTED, request_lang()))


@api_bp.post("/auth/password-reset/confirm")
def confirm_password_reset():
    enforce(f"reset-confirm:ip:{client_ip()}", *RESET_CONFIRMS_PER_IP)
    data = get_json_body()
    token = data.get("token")
    password = require_str(data, "password", max_len=128, min_len=MIN_PASSWORD_LENGTH)
    row = (
        PasswordResetToken.query.filter_by(token_hash=hash_token(token)).first()
        if isinstance(token, str) and token
        else None
    )
    user = db.session.get(User, row.user_id) if row else None
    if row is None or row.used_at is not None or aware(row.expires_at) <= utcnow() or user is None or user.status != "active":
        raise ApiError("reset_link_invalid", "This reset link has expired or was already used. Ask for a new one.", 400)

    user.password_hash = generate_password_hash(password)
    row.used_at = utcnow()
    log_action(organization_id=None, actor_id=user.id, action="user.password_reset", entity_type="user", entity_id=user.id)
    db.session.commit()
    return jsonify(ok=True)
