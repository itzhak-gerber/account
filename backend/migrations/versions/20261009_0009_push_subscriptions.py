"""Web Push subscriptions (notifications on phones and desktops).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-09 08:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "invoice_app"

SECURITY = (
    "ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE push_subscriptions FORCE ROW LEVEL SECURITY",
    # A user manages only their own devices; nobody else can read their endpoints.
    """
    CREATE POLICY push_subscriptions_own ON push_subscriptions FOR ALL
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id())
    """,
    f"GRANT SELECT, INSERT, UPDATE, DELETE ON push_subscriptions TO {APP_ROLE}",
    # The worker sends on behalf of other users: it may read their devices (and only that),
    # and drop a device the push service reports as gone.
    """
    CREATE FUNCTION push_targets(target_users uuid[])
    RETURNS TABLE (id uuid, endpoint text, p256dh text, auth text)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
        SELECT s.id, s.endpoint, s.p256dh, s.auth FROM push_subscriptions s
        WHERE s.user_id = ANY(target_users)
    $$
    """,
    "REVOKE ALL ON FUNCTION push_targets(uuid[]) FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION push_targets(uuid[]) TO {APP_ROLE}",
    """
    CREATE FUNCTION forget_push_subscription(subscription_id uuid) RETURNS void
    LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DELETE FROM push_subscriptions WHERE id = subscription_id
    $$
    """,
    "REVOKE ALL ON FUNCTION forget_push_subscription(uuid) FROM PUBLIC",
    f"GRANT EXECUTE ON FUNCTION forget_push_subscription(uuid) TO {APP_ROLE}",
)

UNDO_SECURITY = (
    "DROP FUNCTION forget_push_subscription(uuid)",
    "DROP FUNCTION push_targets(uuid[])",
)


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(length=1000), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_push_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint("user_id", "endpoint", name="uq_push_subscriptions_device"),
    )
    op.create_index(
        op.f("ix_push_subscriptions_user_id"), "push_subscriptions", ["user_id"], unique=False
    )
    for statement in SECURITY:
        op.execute(statement)


def downgrade() -> None:
    for statement in UNDO_SECURITY:
        op.execute(statement)
    op.drop_index(op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
