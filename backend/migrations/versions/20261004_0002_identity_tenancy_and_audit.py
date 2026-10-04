"""Identity, tenancy and audit: tables, row-level security, app role grants.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04 19:45:10.071343
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APP_ROLE = "invoice_app"
TENANT_TABLES = ("businesses", "business_members", "invitations", "audit_logs")

# Row-level security: every query runs with `app.user_id` and (inside a business)
# `app.business_id` set per transaction by the backend; policies use them to keep each
# business's data separate even if application code forgets a filter.
SECURITY_SQL = [
    f"""
    DO $$ BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            CREATE ROLE {APP_ROLE} NOLOGIN;
        END IF;
    END $$
    """,
    """
    CREATE FUNCTION app_user_id() RETURNS uuid LANGUAGE sql STABLE AS
    $$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$
    """,
    """
    CREATE FUNCTION app_business_id() RETURNS uuid LANGUAGE sql STABLE AS
    $$ SELECT NULLIF(current_setting('app.business_id', true), '')::uuid $$
    """,
    """
    CREATE FUNCTION app_invitation_token_hash() RETURNS text LANGUAGE sql STABLE AS
    $$ SELECT NULLIF(current_setting('app.invitation_token_hash', true), '') $$
    """,
    *[f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY" for t in TENANT_TABLES],
    *[f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY" for t in TENANT_TABLES],
    # A user sees the businesses they belong to; writes only inside the active business.
    """
    CREATE POLICY businesses_select ON businesses FOR SELECT USING (
        id = app_business_id()
        OR EXISTS (SELECT 1 FROM business_members m
                   WHERE m.business_id = businesses.id AND m.user_id = app_user_id())
    )
    """,
    "CREATE POLICY businesses_insert ON businesses FOR INSERT WITH CHECK (id = app_business_id())",
    """
    CREATE POLICY businesses_update ON businesses FOR UPDATE
    USING (id = app_business_id()) WITH CHECK (id = app_business_id())
    """,
    "CREATE POLICY businesses_delete ON businesses FOR DELETE USING (id = app_business_id())",
    # Members of the active business, plus the user's own memberships (for the business list).
    """
    CREATE POLICY business_members_select ON business_members FOR SELECT
    USING (business_id = app_business_id() OR user_id = app_user_id())
    """,
    """
    CREATE POLICY business_members_write ON business_members FOR ALL
    USING (business_id = app_business_id()) WITH CHECK (business_id = app_business_id())
    """,
    # Invitations of the active business; an invitee can read only the one whose token they hold.
    """
    CREATE POLICY invitations_select ON invitations FOR SELECT
    USING (business_id = app_business_id() OR token_hash = app_invitation_token_hash())
    """,
    """
    CREATE POLICY invitations_write ON invitations FOR ALL
    USING (business_id = app_business_id()) WITH CHECK (business_id = app_business_id())
    """,
    """
    CREATE POLICY audit_logs_select ON audit_logs FOR SELECT USING (
        business_id = app_business_id()
        OR (business_id IS NULL AND actor_user_id = app_user_id())
    )
    """,
    """
    CREATE POLICY audit_logs_insert ON audit_logs FOR INSERT
    WITH CHECK (business_id IS NULL OR business_id = app_business_id())
    """,
    # The audit trail is append-only, whoever connects.
    """
    CREATE FUNCTION audit_logs_block_changes() RETURNS trigger LANGUAGE plpgsql AS
    $$ BEGIN RAISE EXCEPTION 'audit_logs is append-only'; END $$
    """,
    """
    CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_block_changes()
    """,
    f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
    f"GRANT SELECT, INSERT, UPDATE ON users TO {APP_ROLE}",
    f"GRANT SELECT, INSERT, UPDATE, DELETE ON businesses, business_members, invitations TO {APP_ROLE}",
    f"GRANT SELECT, INSERT ON audit_logs TO {APP_ROLE}",
]

DOWNGRADE_SECURITY_SQL = [
    "DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs",
    "DROP FUNCTION IF EXISTS audit_logs_block_changes()",
    *[
        f"DROP POLICY IF EXISTS {p} ON {t}"
        for t, p in [
            ("businesses", "businesses_select"),
            ("businesses", "businesses_insert"),
            ("businesses", "businesses_update"),
            ("businesses", "businesses_delete"),
            ("business_members", "business_members_select"),
            ("business_members", "business_members_write"),
            ("invitations", "invitations_select"),
            ("invitations", "invitations_write"),
            ("audit_logs", "audit_logs_select"),
            ("audit_logs", "audit_logs_insert"),
        ]
    ],
    "DROP FUNCTION IF EXISTS app_user_id()",
    "DROP FUNCTION IF EXISTS app_business_id()",
    "DROP FUNCTION IF EXISTS app_invitation_token_hash()",
]


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "businesses",
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("tax_id", sa.String(length=20), nullable=False),
        sa.Column("business_type", sa.String(length=20), nullable=False),
        sa.Column("address_street", sa.String(length=200), nullable=False),
        sa.Column("address_city", sa.String(length=100), nullable=False),
        sa.Column("address_zip", sa.String(length=20), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "business_type IN ('exempt_dealer', 'licensed_dealer', 'company', 'nonprofit')",
            name=op.f("ck_businesses_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_businesses")),
    )
    op.create_table(
        "users",
        sa.Column("idp_subject", sa.String(length=255), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("idp_subject", name=op.f("uq_users_idp_subject")),
    )
    op.create_table(
        "audit_logs",
        sa.Column("business_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_channel", sa.String(length=10), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_audit_logs_actor_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_audit_logs_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_business_id"), "audit_logs", ["business_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)
    op.create_table(
        "business_members",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'accountant', 'member', 'viewer')",
            name=op.f("ck_business_members_role"),
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_business_members_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_business_members_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_members")),
        sa.UniqueConstraint("business_id", "user_id", name=op.f("uq_business_members_business_id")),
    )
    op.create_index(
        op.f("ix_business_members_business_id"), "business_members", ["business_id"], unique=False
    )
    op.create_index(
        op.f("ix_business_members_user_id"), "business_members", ["user_id"], unique=False
    )
    op.create_table(
        "invitations",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("business_name", sa.String(length=200), nullable=False),
        sa.Column("invited_by_name", sa.String(length=200), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'accountant', 'member', 'viewer')",
            name=op.f("ck_invitations_role"),
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            name=op.f("fk_invitations_accepted_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_invitations_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name=op.f("fk_invitations_invited_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invitations_token_hash")),
    )
    op.create_index(
        op.f("ix_invitations_business_id"), "invitations", ["business_id"], unique=False
    )
    # ### end Alembic commands ###

    for statement in SECURITY_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_SECURITY_SQL:
        op.execute(statement)
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_invitations_business_id"), table_name="invitations")
    op.drop_table("invitations")
    op.drop_index(op.f("ix_business_members_user_id"), table_name="business_members")
    op.drop_index(op.f("ix_business_members_business_id"), table_name="business_members")
    op.drop_table("business_members")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_business_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("users")
    op.drop_table("businesses")
    # ### end Alembic commands ###
