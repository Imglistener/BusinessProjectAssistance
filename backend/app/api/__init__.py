from flask import Blueprint, jsonify

from .errors import ApiError

api_bp = Blueprint("api", __name__)


@api_bp.errorhandler(ApiError)
def handle_api_error(e: ApiError):
    body = {"code": e.code, "message": e.message}
    if e.details:
        body["details"] = e.details
    response = jsonify(error=body)
    if e.status == 429 and isinstance(e.details, dict) and "retry_after" in e.details:
        response.headers["Retry-After"] = str(e.details["retry_after"])
    return response, e.status


@api_bp.get("/health")
def health():
    return jsonify(status="ok")


# Import route modules last so they can use api_bp.
from . import activity, ai, attachments, auth, expenses, inventory, members, milestones, notifications, organizations, projects, reports, tasks, trips  # noqa: E402,F401
