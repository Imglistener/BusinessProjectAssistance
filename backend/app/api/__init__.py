from flask import Blueprint, jsonify

from .errors import ApiError

api_bp = Blueprint("api", __name__)


@api_bp.errorhandler(ApiError)
def handle_api_error(e: ApiError):
    body = {"code": e.code, "message": e.message}
    if e.details:
        body["details"] = e.details
    return jsonify(error=body), e.status


@api_bp.get("/health")
def health():
    return jsonify(status="ok")


# Import route modules last so they can use api_bp.
from . import auth, organizations, projects  # noqa: E402,F401
