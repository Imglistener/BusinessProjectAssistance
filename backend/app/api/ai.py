from flask import current_app, jsonify, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import Organization
from ..services import ai_chat, ai_conversations
from ..services.permissions import get_membership
from . import api_bp
from .auth import current_user
from .validation import get_json_body, parse_optional_id


def _org_id(data: dict) -> int:
    org_id = parse_optional_id(data, "organization_id")
    if org_id is None:
        raise ApiError("validation_error", "Organization is required.", 400, {"field": "organization_id"})
    return org_id


@api_bp.post("/ai/chat")
@jwt_required()
def ai_chat_endpoint():
    """Answer a question about the user's organization, and save it in the user's conversation.

    Body: {organization_id, message, project_id?, conversation_id?, history?: [{role, content}]}
    With conversation_id, the saved conversation is the context (history is ignored) and the turn is added to it;
    without, a new conversation starts. The reply carries `conversation` ({id, title, ...}).
    """
    user = current_user()
    data = get_json_body()
    org_id = _org_id(data)
    get_membership(org_id, user.id)
    org = db.session.get(Organization, org_id)
    conversation_id = parse_optional_id(data, "conversation_id")
    conv = ai_conversations.get_owned(user.id, org_id, conversation_id) if conversation_id else None
    history = ai_conversations.history(conv) if conv else data.get("history")
    project_id = parse_optional_id(data, "project_id")
    result = ai_chat.run_chat(user, org, data.get("message"), history, project_id)
    conv = ai_conversations.record(conversation_id, user.id, org_id, project_id, data["message"], result)
    return jsonify({**result, "conversation": ai_conversations.summary(conv)})


@api_bp.get("/ai/conversations")
@jwt_required()
def list_conversations():
    """The user's own conversations in an organization, latest first. Query: organization_id."""
    user = current_user()
    org_id = _org_id({"organization_id": request.args.get("organization_id", type=int)})
    get_membership(org_id, user.id)
    return jsonify(
        conversations=[ai_conversations.summary(c) for c in ai_conversations.list_for(user.id, org_id)],
        retention_days=current_app.config["AI_CONVERSATION_RETENTION_DAYS"],
    )


@api_bp.get("/ai/conversations/<int:conversation_id>")
@jwt_required()
def get_conversation(conversation_id: int):
    user = current_user()
    org_id = _org_id({"organization_id": request.args.get("organization_id", type=int)})
    get_membership(org_id, user.id)
    return jsonify(conversation=ai_conversations.detail(ai_conversations.get_owned(user.id, org_id, conversation_id)))


@api_bp.delete("/ai/conversations/<int:conversation_id>")
@jwt_required()
def delete_conversation(conversation_id: int):
    user = current_user()
    org_id = _org_id({"organization_id": request.args.get("organization_id", type=int)})
    get_membership(org_id, user.id)
    ai_conversations.delete(ai_conversations.get_owned(user.id, org_id, conversation_id))
    db.session.commit()
    return jsonify(ok=True)


@api_bp.delete("/ai/conversations")
@jwt_required()
def delete_all_conversations():
    """Delete all of the user's conversations in an organization. Query: organization_id."""
    user = current_user()
    org_id = _org_id({"organization_id": request.args.get("organization_id", type=int)})
    get_membership(org_id, user.id)
    deleted = ai_conversations.delete_for(user.id, org_id)
    db.session.commit()
    return jsonify(deleted=deleted)
