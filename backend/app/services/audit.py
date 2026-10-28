from ..extensions import db
from ..models import AuditLog


def log_action(*, organization_id, actor_id, action, entity_type, entity_id=None, meta=None):
    """Stage an audit entry in the current session; the caller commits.

    Keep `meta` small and free of secrets or sensitive business data.
    """
    entry = AuditLog(
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=meta,
    )
    db.session.add(entry)
    return entry
