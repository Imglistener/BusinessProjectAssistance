import re

from flask import jsonify
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import OrganizationMember, User
from . import api_bp
from .errors import ApiError
from .validation import get_json_body, require_str

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
    }


def current_user() -> User:
    """Resolve the authenticated user; call only inside a @jwt_required() view."""
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or user.status != "active":
        raise ApiError("unauthorized", "Account not available.", 401)
    return user


@api_bp.post("/auth/register")
def register():
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
    )
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token, user=user_to_dict(user)), 201


@api_bp.post("/auth/login")
def login():
    data = get_json_body()
    email = require_str(data, "email").lower()
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    # One generic error for unknown email and wrong password.
    if (
        user is None
        or user.status != "active"
        or not isinstance(password, str)
        or not check_password_hash(user.password_hash, password)
    ):
        raise ApiError("invalid_credentials", "Incorrect email or password.", 401)

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
