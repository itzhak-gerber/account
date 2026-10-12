"""Operator overview of all businesses, and plan expiry reminders

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-12 20:00:00.000000

Both cross every business, so they are SECURITY DEFINER functions (like the other daily jobs).
The application calls admin_businesses only for signed-in operators.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "invoice_app"

ADMIN_BUSINESSES = """
CREATE FUNCTION admin_businesses(on_day date) RETURNS TABLE (
    id uuid, display_name text, legal_name text, tax_id text, created_at timestamptz,
    owner_email text, subscription_id uuid, kind text, plan_name text, ends_on date,
    documents_this_month bigint, scans_this_month bigint
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT b.id, b.display_name::text, b.legal_name::text, b.tax_id::text, b.created_at,
           (SELECT u.email::text FROM business_members m JOIN users u ON u.id = m.user_id
            WHERE m.business_id = b.id AND m.role = 'owner'
            ORDER BY m.created_at LIMIT 1),
           s.id, s.kind::text, s.terms ->> 'name', s.ends_on,
           (SELECT count(*) FROM usage_events e
            WHERE e.business_id = b.id AND e.kind = 'document'
              AND e.month = date_trunc('month', on_day)::date),
           (SELECT count(*) FROM usage_events e
            WHERE e.business_id = b.id AND e.kind = 'scan'
              AND e.month = date_trunc('month', on_day)::date)
    FROM businesses b
    LEFT JOIN LATERAL (
        SELECT * FROM subscriptions s
        WHERE s.business_id = b.id AND s.starts_on <= on_day
          AND (s.ends_on IS NULL OR s.ends_on > on_day)
        ORDER BY s.starts_on DESC, s.created_at DESC LIMIT 1
    ) s ON true
    ORDER BY b.created_at DESC
$$
"""

# 14 and 3 days before the business's last subscription ends, and on the day it ends.
PLAN_REMINDERS = """
CREATE FUNCTION enqueue_plan_reminders(on_day date) RETURNS integer
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $$
    WITH last_sub AS (
        SELECT DISTINCT ON (business_id) business_id, id, ends_on
        FROM subscriptions
        ORDER BY business_id, (ends_on IS NULL) DESC, ends_on DESC
    ), due AS (
        SELECT business_id, id, ends_on, (ends_on - on_day) AS days
        FROM last_sub
        WHERE ends_on IS NOT NULL AND (ends_on - on_day) IN (14, 3, 0)
    ), queued AS (
        INSERT INTO outbox_events
            (id, business_id, event_type, payload, status, attempts, available_at, created_at)
        SELECT gen_random_uuid(), d.business_id, 'plan.expiring',
               jsonb_build_object('subscription_id', d.id, 'ends_on', d.ends_on, 'days', d.days),
               'pending', 0, now(), now()
        FROM due d
        WHERE NOT EXISTS (
            SELECT 1 FROM outbox_events e
            WHERE e.business_id = d.business_id AND e.event_type = 'plan.expiring'
              AND e.payload ->> 'subscription_id' = d.id::text
              AND (e.payload ->> 'days')::int = d.days
        )
        RETURNING 1
    )
    SELECT count(*)::integer FROM queued
$$
"""


def upgrade() -> None:
    op.execute(ADMIN_BUSINESSES)
    op.execute("REVOKE ALL ON FUNCTION admin_businesses(date) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION admin_businesses(date) TO {APP_ROLE}")
    op.execute(PLAN_REMINDERS)
    op.execute("REVOKE ALL ON FUNCTION enqueue_plan_reminders(date) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION enqueue_plan_reminders(date) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION enqueue_plan_reminders(date)")
    op.execute("DROP FUNCTION admin_businesses(date)")
