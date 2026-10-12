"""Per-user display preferences: theme and text size

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-12 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("theme", sa.String(length=10), server_default="system", nullable=False)
    )
    op.add_column(
        "users",
        sa.Column("text_size", sa.String(length=10), server_default="device", nullable=False),
    )
    op.create_check_constraint("theme", "users", "theme IN ('system', 'light', 'dark')")
    op.create_check_constraint("text_size", "users", "text_size IN ('device', 'large', 'xlarge')")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_text_size"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_theme"), "users", type_="check")
    op.drop_column("users", "text_size")
    op.drop_column("users", "theme")
