"""Delivery notes (תעודת משלוח) as a document type

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-09 13:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = (
    "quote",
    "proforma_invoice",
    "tax_invoice",
    "receipt",
    "tax_invoice_receipt",
    "credit_note",
)
AFTER = (*BEFORE, "delivery_note")


def _check(types: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_documents_type"), "documents", type_="check")
    op.create_check_constraint(
        "type", "documents", "type IN (" + ", ".join(f"'{t}'" for t in types) + ")"
    )


def upgrade() -> None:
    _check(AFTER)


def downgrade() -> None:
    # Issued documents can never be deleted, so a database with delivery notes stays on 0013.
    _check(BEFORE)
