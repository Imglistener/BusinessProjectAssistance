from flask import jsonify
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import Organization
from ..services import ai_chat
from ..services.permissions import get_membership
from . import api_bp
from .auth import current_user
from .validation import get_json_body, parse_optional_id


@api_bp.post("/ai/chat")
@jwt_required()
def ai_chat_endpoint():
    """Answer a question about the user's organization with read-only tools.

    Body: {organization_id, message, project_id?, history?: [{role, content}]}
    """
    user = current_user()
    data = get_json_body()
    org_id = parse_optional_id(data, "organization_id")
    if org_id is None:
        raise ApiError("validation_error", "Organization is required.", 400, {"field": "organization_id"})
    get_membership(org_id, user.id)
    org = db.session.get(Organization, org_id)
    result = ai_chat.run_chat(
        user, org, data.get("message"), data.get("history"), parse_optional_id(data, "project_id")
    )
    return jsonify(result)
