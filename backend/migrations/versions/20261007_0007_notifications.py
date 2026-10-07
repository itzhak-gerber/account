"""Notifications: in-app inbox, preferences, and the outbox dispatcher's database functions.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-07 07:59:30.932795
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "invoice_app"

SECURITY = (
    "ALTER TABLE notifications ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE notifications FORCE ROW LEVEL SECURITY",
    # Each user reads and marks only their own notifications.
    "CREATE POLICY notifications_own ON notifications FOR SELECT USING (user_id = app_user_id())",
    """
    CREATE POLICY notifications_mark_read ON notifications FOR UPDATE
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id())
    """,
    # Written inside a business, only for that business's members.
    """
    CREATE POLICY notifications_insert ON notifications FOR INSERT WITH CHECK (
        business_id = app_business_id()
        AND EXISTS (SELECT 1 FROM business_members m
                    WHERE m.business_id = notifications.business_id
                      AND m.user_id = notifications.user_id)
    )
    """,
    "ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE notification_preferences FORCE ROW LEVEL SECURITY",
    """
    CREATE POLICY notification_preferences_own ON notification_preferences FOR ALL
    USING (user_id = app_user_id()) WITH CHECK (user_id = app_user_id())
    """,
    # The dispatcher reads the preferences of the active business's members.
    """
    CREATE POLICY notification_preferences_business ON notification_preferences FOR SELECT
    USING (user_id IN (SELECT m.user_id FROM business_members m
                       WHERE m.business_id = app_business_id()))
    """,
    f"GRANT SELECT, INSERT, UPDATE ON notifications TO {APP_ROLE}",
    f"GRANT SELECT, INSERT, UPDATE, DELETE ON notification_preferences TO {APP_ROLE}",
    # The functions below run as the schema owner (the migration role). These policies let that
    # role, and only it, work across businesses; the app role still sees one business at a time.
    "CREATE POLICY outbox_events_owner ON outbox_events FOR ALL TO CURRENT_USER USING (true)",
    "CREATE POLICY documents_owner_read ON documents FOR SELECT TO CURRENT_USER USING (true)",
    "CREATE POLICY notifications_owner ON notifications FOR ALL TO CURRENT_USER USING (true)",
    # Hand out pending events across businesses, each leased for a while so a crashed worker's
    # events are picked up again.
    """
    CREATE FUNCTION claim_outbox_events(max_events integer, lease_seconds integer)
    RETURNS TABLE (id uuid, business_id uuid, event_type text, payload jsonb, attempts integer)
    LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        UPDATE outbox_events o
        SET status = 'processing', attempts = o.attempts + 1,
            available_at = now() + make_interval(secs => lease_seconds)
        WHERE o.id IN (
            SELECT e.id FROM outbox_events e
            WHERE e.status IN ('pending', 'processing') AND e.available_at <= now()
            ORDER BY e.created_at
            LIMIT max_events
            FOR UPDATE SKIP LOCKED
        )
        RETURNING o.id, o.business_id, o.event_type::text, o.payload, o.attempts
    $$
    """,
    # Raise one event per invoice whose due date (or issue date) fell in the window and that is
    # still open. Already-raised invoices are skipped.
    """
    CREATE FUNCTION enqueue_overdue_events(since date, until date) RETURNS integer
    LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        WITH due AS (
            INSERT INTO outbox_events
                (id, business_id, event_type, payload, status, attempts, available_at, created_at)
            SELECT gen_random_uuid(), d.business_id, 'invoice.overdue',
                   jsonb_build_object('document_id', d.id::text,
                                      'due_date', COALESCE(d.due_date, d.issue_date)),
                   'pending', 0, now(), now()
            FROM documents d
            WHERE d.status = 'issued'
              AND d.type IN ('tax_invoice', 'proforma_invoice')
              AND d.superseded_by_id IS NULL
              AND d.total - d.amount_paid - d.amount_credited > 0
              AND COALESCE(d.due_date, d.issue_date) BETWEEN since AND until
              AND NOT EXISTS (
                  SELECT 1 FROM outbox_events e
                  WHERE e.event_type = 'invoice.overdue'
                    AND e.payload ->> 'document_id' = d.id::text
              )
            RETURNING 1
        )
        SELECT count(*)::integer FROM due
    $$
    """,
    # Housekeeping: drop handled events after 30 days and read notifications after 180.
    """
    CREATE FUNCTION purge_old_notifications() RETURNS void
    LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        DELETE FROM outbox_events
        WHERE status IN ('done', 'failed') AND created_at < now() - interval '30 days';
        DELETE FROM notifications
        WHERE read_at IS NOT NULL AND created_at < now() - interval '180 days';
    $$
    """,
    *[
        f"REVOKE ALL ON FUNCTION {f} FROM PUBLIC"
        for f in (
            "claim_outbox_events(integer, integer)",
            "enqueue_overdue_events(date, date)",
            "purge_old_notifications()",
        )
    ],
    *[
        f"GRANT EXECUTE ON FUNCTION {f} TO {APP_ROLE}"
        for f in (
            "claim_outbox_events(integer, integer)",
            "enqueue_overdue_events(date, date)",
            "purge_old_notifications()",
        )
    ],
    # Events written before the dispatcher existed are history, not news.
    "UPDATE outbox_events SET status = 'done' WHERE status = 'pending'",
)

UNDO_SECURITY = (
    "DROP FUNCTION purge_old_notifications()",
    "DROP FUNCTION enqueue_overdue_events(date, date)",
    "DROP FUNCTION claim_outbox_events(integer, integer)",
    "DROP POLICY documents_owner_read ON documents",
    "DROP POLICY outbox_events_owner ON outbox_events",
)


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(length=30), nullable=False),
        sa.Column(
            "channels",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_preferences_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "event", name=op.f("pk_notification_preferences")),
    )
    op.create_table(
        "notifications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("link", sa.String(length=300), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_notifications_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
    )
    op.create_index(
        op.f("ix_notifications_business_id"), "notifications", ["business_id"], unique=False
    )
    op.create_index(
        "ix_notifications_inbox",
        "notifications",
        ["user_id", "business_id", "created_at"],
        unique=False,
    )
    # ### end Alembic commands ###
    for statement in SECURITY:
        op.execute(statement)


def downgrade() -> None:
    for statement in UNDO_SECURITY:
        op.execute(statement)
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_notifications_inbox", table_name="notifications")
    op.drop_index(op.f("ix_notifications_business_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("notification_preferences")
    # ### end Alembic commands ###
