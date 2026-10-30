"""Receipts and other files attached to expenses.

Anyone who can see the project can view them; whoever can change the expense can add or remove them.
Downloads always go through this permission-checked endpoint and are served as attachments.
"""
from __future__ import annotations

import io
from urllib.parse import quote

from flask import current_app, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import Attachment, ExpenseStatus, User
from ..services import projects as svc
from ..services import storage
from ..services.audit import log_action
from ..services.tokens import aware
from . import api_bp
from .auth import current_user
from .expenses import _require_can_modify, get_expense_for_user

MAX_FILES_PER_EXPENSE = 10


def attachment_to_dict(a: Attachment, names: dict) -> dict:
    return {
        "id": a.id,
        "expense_id": a.expense_id,
        "filename": a.filename,
        "content_type": a.content_type,
        "size": a.size,
        "uploaded_by": names.get(a.uploaded_by),
        "created_at": aware(a.created_at).isoformat(),
    }


def _names(rows) -> dict:
    ids = {a.uploaded_by for a in rows}
    return {u.id: f"{u.first_name} {u.last_name}" for u in User.query.filter(User.id.in_(ids))} if ids else {}


def _audit(user_id, project, action, attachment) -> None:
    log_action(
        organization_id=project.organization_id,
        actor_id=user_id,
        action=action,
        entity_type="attachment",
        entity_id=attachment.id,
        meta={"project_id": project.id, "expense_id": attachment.expense_id, "filename": attachment.filename},
    )


@api_bp.get("/expenses/<int:expense_id>/attachments")
@jwt_required()
def list_attachments(expense_id: int):
    user = current_user()
    expense, _, _ = get_expense_for_user(expense_id, user.id)
    rows = Attachment.query.filter_by(expense_id=expense.id).order_by(Attachment.created_at, Attachment.id).all()
    return jsonify(attachments=[attachment_to_dict(a, _names(rows)) for a in rows])


@api_bp.post("/expenses/<int:expense_id>/attachments")
@jwt_required()
def upload_attachment(expense_id: int):
    user = current_user()
    expense, project, membership = get_expense_for_user(expense_id, user.id)
    _require_can_modify(expense, membership, user.id)
    svc.require_active_project(project)
    if expense.status != ExpenseStatus.VALID:
        raise ApiError("expense_not_editable", "Files can only be added to valid expenses.", 409)
    if Attachment.query.filter_by(expense_id=expense.id).count() >= MAX_FILES_PER_EXPENSE:
        raise ApiError("too_many_files", f"An expense can have at most {MAX_FILES_PER_EXPENSE} files.", 409)

    upload = request.files.get("file")
    if upload is None:
        raise ApiError("validation_error", "Choose a file to upload.", 400, {"field": "file"})
    limit = current_app.config["MAX_UPLOAD_MB"] * 1024 * 1024
    data = upload.read(limit + 1)
    if not data:
        raise ApiError("validation_error", "That file is empty.", 400, {"field": "file"})
    if len(data) > limit:
        raise ApiError("file_too_large", f"Files can be at most {current_app.config['MAX_UPLOAD_MB']} MB.", 413, {"field": "file"})
    kind = storage.sniff(data[:16])
    if kind is None:
        raise ApiError("unsupported_file", "Upload a PDF, JPEG, PNG or WebP file.", 415, {"field": "file"})
    content_type, ext = kind

    stored_name = storage.save(data)
    attachment = Attachment(
        organization_id=project.organization_id,
        expense_id=expense.id,
        filename=storage.clean_filename(upload.filename, ext),
        stored_name=stored_name,
        content_type=content_type,
        size=len(data),
        uploaded_by=user.id,
    )
    try:
        db.session.add(attachment)
        db.session.flush()
        _audit(user.id, project, "attachment.added", attachment)
        db.session.commit()
    except Exception:
        db.session.rollback()
        storage.delete(stored_name)  # don't leave an orphan file behind
        raise
    return jsonify(attachment=attachment_to_dict(attachment, {user.id: f"{user.first_name} {user.last_name}"})), 201


def _attachment_for_user(attachment_id: int, user_id: int):
    attachment = db.session.get(Attachment, attachment_id)
    if attachment is None:
        raise ApiError("not_found", "File not found.", 404)
    try:
        expense, project, membership = get_expense_for_user(attachment.expense_id, user_id)
    except ApiError:
        raise ApiError("not_found", "File not found.", 404)
    return attachment, expense, project, membership


@api_bp.get("/attachments/<int:attachment_id>/file")
@jwt_required()
def download_attachment(attachment_id: int):
    user = current_user()
    attachment, _, _, _ = _attachment_for_user(attachment_id, user.id)
    try:
        # Read it whole (files are small): no open handle is left behind, so it can be deleted at any time.
        data = storage.read(attachment.stored_name)
    except FileNotFoundError:
        raise ApiError("file_missing", "This file is no longer available.", 410)
    response = send_file(io.BytesIO(data), mimetype=attachment.content_type, max_age=0)
    # Always a download: the browser must not render user-uploaded content inline on our origin.
    ascii_name = attachment.filename.encode("ascii", "replace").decode().replace('"', "'").replace("?", "_")
    response.headers["Content-Disposition"] = (
        f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(attachment.filename)}"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@api_bp.delete("/attachments/<int:attachment_id>")
@jwt_required()
def delete_attachment(attachment_id: int):
    user = current_user()
    attachment, expense, project, membership = _attachment_for_user(attachment_id, user.id)
    _require_can_modify(expense, membership, user.id)
    svc.require_active_project(project)
    stored_name = attachment.stored_name
    _audit(user.id, project, "attachment.removed", attachment)
    db.session.delete(attachment)
    db.session.commit()
    storage.delete(stored_name)
    return jsonify(ok=True)
