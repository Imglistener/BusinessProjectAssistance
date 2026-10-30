import re

from flask import Response, jsonify
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models import Organization
from ..services import projects as svc
from ..services import reports
from . import api_bp
from .auth import current_user


def _project(project_id: int):
    user = current_user()
    project, _ = svc.get_project_for_user(project_id, user.id)
    return project, db.session.get(Organization, project.organization_id)


def _filename(project, kind: str, as_of: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", project.name.lower()).strip("-")[:50] or f"project-{project.id}"
    return f"{slug}-{kind}-{as_of}.csv"


def _csv_response(body: str, filename: str) -> Response:
    return Response(
        body,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@api_bp.get("/projects/<int:project_id>/report")
@jwt_required()
def project_report(project_id: int):
    project, org = _project(project_id)
    return jsonify(report=reports.build_report(project, org))


@api_bp.get("/projects/<int:project_id>/expenses.csv")
@jwt_required()
def export_expenses(project_id: int):
    project, org = _project(project_id)
    as_of = svc.org_today(org.timezone).isoformat()
    return _csv_response(reports.expenses_csv(project), _filename(project, "expenses", as_of))


@api_bp.get("/projects/<int:project_id>/tasks.csv")
@jwt_required()
def export_tasks(project_id: int):
    project, org = _project(project_id)
    as_of = svc.org_today(org.timezone).isoformat()
    return _csv_response(reports.tasks_csv(project, org), _filename(project, "tasks", as_of))
