"""Baseline: the schema that sql/schema.sql and its deltas 001-007 described.

Revision ID: 0001
Revises:
Create Date: 2026-11-10

Written once from the ORM and checked against the SQL schema (same columns, types,
defaults, constraints and indexes; only the names follow the naming convention).
Databases created with sql/ are not stamped: recreate them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=True),
        sa.Column("correlation_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default="5", nullable=False),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "handler_state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSED', 'FAILED')", name=op.f("ck_outbox_events_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
    )
    op.create_index(
        "ix_outbox_events_aggregate_id",
        "outbox_events",
        ["aggregate_id"],
        unique=False,
        postgresql_where=sa.text("aggregate_id IS NOT NULL"),
    )
    op.create_index(
        "ix_outbox_events_correlation_id",
        "outbox_events",
        ["correlation_id"],
        unique=False,
        postgresql_where=sa.text("correlation_id IS NOT NULL"),
    )
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["scheduled_at"],
        unique=False,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_table(
        "permissions",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("name", name=op.f("uq_permissions_name")),
    )
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("jti", name=op.f("pk_revoked_tokens")),
    )
    op.create_index(
        op.f("ix_revoked_tokens_expires_at"), "revoked_tokens", ["expires_at"], unique=False
    )
    op.create_table(
        "roles",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
    )
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("job_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_run_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("run_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("claimed_by", sa.Text(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'DISABLED')", name=op.f("ck_scheduled_jobs_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scheduled_jobs")),
        sa.UniqueConstraint("job_name", name=op.f("uq_scheduled_jobs_job_name")),
    )
    op.create_index(
        "ix_scheduled_jobs_pending",
        "scheduled_jobs",
        ["next_run_at"],
        unique=False,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(
        "ix_users_is_active",
        "users",
        ["is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "uq_users_email_lower", "users", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_index(
        "uq_users_username_lower", "users", [sa.literal_column("lower(username)")], unique=True
    )
    op.create_table(
        "items",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), server_default="general", nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_items_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_items")),
    )
    op.create_index(op.f("ix_items_category"), "items", ["category"], unique=False)
    op.create_index("ix_items_created_at", "items", ["created_at"], unique=False)
    op.create_index(
        "ix_items_is_active",
        "items",
        ["is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(op.f("ix_items_owner_id"), "items", ["owner_id"], unique=False)
    op.create_index(op.f("ix_items_priority"), "items", ["priority"], unique=False)
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("fk_role_permissions_permission_id_permissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("pk_role_permissions")),
    )
    op.create_index(
        "ix_role_permissions_permission_id", "role_permissions", ["permission_id"], unique=False
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name=op.f("fk_user_roles_role_id_roles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_roles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_user_roles")),
    )
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"], unique=False)


def downgrade() -> None:
    # Dropping a table drops its indexes and constraints; dependents go first.
    for table in (
        "user_roles",
        "role_permissions",
        "items",
        "users",
        "scheduled_jobs",
        "roles",
        "revoked_tokens",
        "permissions",
        "outbox_events",
    ):
        op.drop_table(table)
