"""Full data exports (ZIP of document copies, spreadsheets and the uniform-format file).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_exports",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("documents", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"], name=op.f("fk_data_exports_business_id_businesses")
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name=op.f("fk_data_exports_requested_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_exports")),
    )
    op.create_index(
        op.f("ix_data_exports_business_id"), "data_exports", ["business_id"], unique=False
    )
    op.execute("ALTER TABLE data_exports ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE data_exports FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY data_exports_tenant ON data_exports FOR ALL "
        "USING (business_id = app_business_id()) WITH CHECK (business_id = app_business_id())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON data_exports TO invoice_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS data_exports_tenant ON data_exports")
    op.drop_index(op.f("ix_data_exports_business_id"), table_name="data_exports")
    op.drop_table("data_exports")
