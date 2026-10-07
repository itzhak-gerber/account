"""Role-based permissions inside a business. Checked in the service layer for every channel."""

import enum

from app.core.errors import Forbidden
from app.models import Role


class Permission(enum.StrEnum):
    VIEW_BUSINESS = "view_business"
    MANAGE_BUSINESS = "manage_business"
    VIEW_MEMBERS = "view_members"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_OWNERS = "manage_owners"
    VIEW_AUDIT_LOG = "view_audit_log"
    VIEW_CATALOG = "view_catalog"
    MANAGE_CATALOG = "manage_catalog"
    VIEW_DOCUMENTS = "view_documents"
    EDIT_DRAFTS = "edit_drafts"
    ISSUE_DOCUMENTS = "issue_documents"
    VIEW_REPORTS = "view_reports"


_ALL = frozenset(Permission)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _ALL,
    Role.ADMIN: _ALL - {Permission.MANAGE_OWNERS},
    Role.ACCOUNTANT: frozenset(
        {
            Permission.VIEW_BUSINESS,
            Permission.VIEW_MEMBERS,
            Permission.VIEW_AUDIT_LOG,
            Permission.VIEW_CATALOG,
            Permission.VIEW_DOCUMENTS,
            Permission.VIEW_REPORTS,
        }
    ),
    Role.MEMBER: frozenset(
        {
            Permission.VIEW_BUSINESS,
            Permission.VIEW_MEMBERS,
            Permission.VIEW_CATALOG,
            Permission.MANAGE_CATALOG,
            Permission.VIEW_DOCUMENTS,
            Permission.EDIT_DRAFTS,
            Permission.ISSUE_DOCUMENTS,
            Permission.VIEW_REPORTS,
        }
    ),
    Role.VIEWER: frozenset(
        {Permission.VIEW_BUSINESS, Permission.VIEW_CATALOG, Permission.VIEW_DOCUMENTS}
    ),
}

# Roles whose holders must sign in with two-factor authentication.
MFA_REQUIRED_ROLES = frozenset({Role.OWNER, Role.ADMIN})


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def require(role: Role, permission: Permission) -> None:
    if not has_permission(role, permission):
        raise Forbidden(f"Role '{role}' lacks permission '{permission}'", code="permission_denied")
