"""Remove the items example: its table and its permissions.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-10

Workshops replaced items as the example context. This is also what removing an example
context looks like in a project that starts from the boilerplate: drop its tables and
delete its permissions; the grants to roles go with them (ON DELETE CASCADE).

The downgrade brings back the empty table and the permissions as revision 0004 left
them. The rows are not recoverable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("items:read", "View items"),
    ("items:write", "Create and modify items"),
    ("items:delete", "Delete items"),
    ("items:manage", "Read, modify and delete the items of any owner"),
]
GRANTS = {
    "admin": [name for name, _ in PERMISSIONS],
    "user": ["items:read", "items:write", "items:delete"],
}

roles = sa.table("roles", sa.column("id", sa.BigInteger), sa.column("name"))
permissions = sa.table(
    "permissions", sa.column("id", sa.BigInteger), sa.column("name"), sa.column("description")
)
role_permissions = sa.table(
    "role_permissions",
    sa.column("role_id", sa.BigInteger),
    sa.column("permission_id", sa.BigInteger),
)


def upgrade() -> None:
    op.drop_table("items")
    op.execute(permissions.delete().where(permissions.c.name.in_([n for n, _ in PERMISSIONS])))


def downgrade() -> None:
    op.bulk_insert(permissions, [{"name": n, "description": d} for n, d in PERMISSIONS])
    conn = op.get_bind()
    role_ids = dict(conn.execute(sa.select(roles.c.name, roles.c.id)).all())
    permission_ids = dict(conn.execute(sa.select(permissions.c.name, permissions.c.id)).all())
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_ids[role], "permission_id": permission_ids[permission]}
            for role, granted in GRANTS.items()
            for permission in granted
        ],
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
    op.create_index(op.f("ix_items_category"), "items", ["category"])
    op.create_index("ix_items_created_at", "items", ["created_at"])
    op.create_index(
        "ix_items_is_active",
        "items",
        ["is_active"],
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(op.f("ix_items_owner_id"), "items", ["owner_id"])
    op.create_index(op.f("ix_items_priority"), "items", ["priority"])
