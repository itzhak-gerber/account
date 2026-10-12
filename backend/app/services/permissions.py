"""Role-based permissions inside a business. Checked in the service layer for every channel."""

import enum
from typing import Protocol

from app.core.errors import Forbidden
from app.models import Role
from app.services.access import Access


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
    # Suppliers, purchase orders, goods receipts and supplier invoices.
    VIEW_PURCHASING = "view_purchasing"
    MANAGE_PURCHASING = "manage_purchasing"
    # Download everything (all documents, customers, items): owners, admins and accountants.
    EXPORT_DATA = "export_data"


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
            Permission.VIEW_PURCHASING,
            Permission.EXPORT_DATA,
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
            Permission.VIEW_PURCHASING,
            Permission.MANAGE_PURCHASING,
        }
    ),
    Role.VIEWER: frozenset(
        {Permission.VIEW_BUSINESS, Permission.VIEW_CATALOG, Permission.VIEW_DOCUMENTS}
    ),
}

# Roles whose holders must sign in with two-factor authentication.
MFA_REQUIRED_ROLES = frozenset({Role.OWNER, Role.ADMIN})


# What a read-only business (no current plan) cannot do. Managing members, the business's
# details and exports stay open, so the owner can still reach and take out their records.
CHANGES_DATA = frozenset(
    {
        Permission.MANAGE_CATALOG,
        Permission.EDIT_DRAFTS,
        Permission.ISSUE_DOCUMENTS,
        Permission.MANAGE_PURCHASING,
    }
)


class Context(Protocol):
    @property
    def role(self) -> Role: ...
    @property
    def access(self) -> Access: ...


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def require(ctx: Context, permission: Permission, *, while_read_only: bool = False) -> None:
    """The role must allow it, and a read-only business cannot change its data.

    ``while_read_only`` is for actions on documents already issued (emailing one, asking again
    for its allocation number), which finish what was done before the plan ended."""
    if not has_permission(ctx.role, permission):
        raise Forbidden(
            f"Role '{ctx.role}' lacks permission '{permission}'", code="permission_denied"
        )
    if permission in CHANGES_DATA and not while_read_only:
        ctx.access.require_writable()
