from ..extensions import db
from ..models import AuditLog


def project_id_for(entity_type, entity_id, meta):
    """The project an entry belongs to: the project itself, or meta["project_id"] for its records."""
    if entity_type == "project":
        return entity_id
    if isinstance(meta, dict) and isinstance(meta.get("project_id"), int):
        return meta["project_id"]
    return None


def log_action(*, organization_id, actor_id, action, entity_type, entity_id=None, meta=None):
    """Stage an audit entry in the current session; the caller commits.

    Keep `meta` small and free of secrets or sensitive business data.
    """
    entry = AuditLog(
        organization_id=organization_id,
        project_id=project_id_for(entity_type, entity_id, meta),
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=meta,
    )
    db.session.add(entry)
    return entry
