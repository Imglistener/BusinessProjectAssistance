from ..errors import ApiError
from ..models import OrganizationMember, Role

# Roles allowed to manage organization members/settings (to confirm with the project owner).
ORG_ADMIN_ROLES = (Role.OWNER,)


def get_membership(organization_id: int, user_id: int) -> OrganizationMember:
    """Return the user's active membership or raise 404.

    404 (not 403) so outsiders cannot discover which organization IDs exist.
    """
    membership = OrganizationMember.query.filter_by(
        organization_id=organization_id, user_id=user_id, status="active"
    ).first()
    if membership is None:
        raise ApiError("not_found", "Organization not found.", 404)
    return membership


def require_role(membership: OrganizationMember, *roles: Role) -> None:
    if membership.role not in roles:
        raise ApiError("forbidden", "You do not have permission to do this.", 403)
