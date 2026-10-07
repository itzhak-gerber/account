"""Proformas are closed by the tax invoice issued from them.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-07 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PREVIOUS_MUTABLE = (
    "original_pdf_file_id",
    "original_delivered_at",
    "amount_paid",
    "allocation_number",
    "updated_at",
    "amount_credited",
)
MUTABLE_AFTER_ISSUE = (*PREVIOUS_MUTABLE, "superseded_by_id")


def guard_function(mutable: tuple[str, ...]) -> str:
    """Issued documents stay frozen except for the listed bookkeeping columns."""
    columns = ", ".join(f"'{c}'" for c in mutable)
    return f"""
    CREATE OR REPLACE FUNCTION documents_guard_issued() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            IF OLD.status = 'issued' THEN
                RAISE EXCEPTION 'issued documents cannot be deleted';
            END IF;
            RETURN OLD;
        END IF;
        IF OLD.status = 'issued' AND (to_jsonb(NEW) - ARRAY[{columns}])
            IS DISTINCT FROM (to_jsonb(OLD) - ARRAY[{columns}]) THEN
            RAISE EXCEPTION 'issued documents cannot be changed';
        END IF;
        RETURN NEW;
    END $$
    """


def upgrade() -> None:
    op.add_column("documents", sa.Column("superseded_by_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_documents_superseded_by_id_documents",
        "documents",
        "documents",
        ["superseded_by_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(guard_function(MUTABLE_AFTER_ISSUE))
    # Backfill: close proformas that already have an issued tax invoice (or invoice-receipt)
    # made from them, and carry what was paid on the proforma over to the tax invoice.
    op.execute("""
        WITH successor AS (
            SELECT DISTINCT ON (r.to_document_id)
                   r.to_document_id AS proforma_id, d.id AS invoice_id, d.type AS invoice_type
            FROM document_relations r
            JOIN documents d ON d.id = r.from_document_id
            JOIN documents p ON p.id = r.to_document_id
            WHERE r.relation = 'converted_from' AND d.status = 'issued'
              AND d.type IN ('tax_invoice', 'tax_invoice_receipt')
              AND p.type = 'proforma_invoice' AND p.status = 'issued'
            ORDER BY r.to_document_id, d.issued_at
        ), closed AS (
            UPDATE documents p SET superseded_by_id = s.invoice_id
            FROM successor s WHERE p.id = s.proforma_id
            RETURNING s.invoice_id, s.invoice_type, p.amount_paid
        )
        UPDATE documents i
        SET amount_paid = LEAST(i.total - i.amount_credited, i.amount_paid + c.amount_paid)
        FROM closed c
        WHERE i.id = c.invoice_id AND c.invoice_type = 'tax_invoice' AND c.amount_paid > 0
    """)


def downgrade() -> None:
    op.execute(guard_function(PREVIOUS_MUTABLE))
    op.drop_constraint("fk_documents_superseded_by_id_documents", "documents", type_="foreignkey")
    op.drop_column("documents", "superseded_by_id")
