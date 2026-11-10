"""Permissions the item routes now check: items:manage, and items:delete for the user role.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10

The item routes require a permission, and an item belongs to its owner unless the caller
holds items:manage. Accounts that registered before roles were assigned get the user
role, or they would lose access to their own items.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MANAGE = ("items:manage", "Read, modify and delete the items of any owner")
# role -> permissions granted by this migration
GRANTS = {"admin": ["items:manage"], "user": ["items:delete"]}

roles = sa.table("roles", sa.column("id", sa.BigInteger), sa.column("name"))
permissions = sa.table(
    "permissions", sa.column("id", sa.BigInteger), sa.column("name"), sa.column("description")
)
role_permissions = sa.table(
    "role_permissions",
    sa.column("role_id", sa.BigInteger),
    sa.column("permission_id", sa.BigInteger),
)
users = sa.table("users", sa.column("id", sa.BigInteger))
user_roles = sa.table(
    "user_roles", sa.column("user_id", sa.BigInteger), sa.column("role_id", sa.BigInteger)
)


def _ids(conn: sa.Connection, table: sa.TableClause) -> dict[str, int]:
    return {name: id_ for name, id_ in conn.execute(sa.select(table.c.name, table.c.id))}


def upgrade() -> None:
    op.bulk_insert(permissions, [{"name": MANAGE[0], "description": MANAGE[1]}])

    conn = op.get_bind()
    role_ids, permission_ids = _ids(conn, roles), _ids(conn, permissions)
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_ids[role], "permission_id": permission_ids[permission]}
            for role, granted in GRANTS.items()
            for permission in granted
        ],
    )

    has_a_role = sa.select(user_roles.c.user_id)
    op.execute(
        user_roles.insert().from_select(
            ["user_id", "role_id"],
            sa.select(users.c.id, sa.literal(role_ids["user"], sa.BigInteger)).where(
                users.c.id.not_in(has_a_role)
            ),
        )
    )


def downgrade() -> None:
    # The user role given to accounts that had none stays: nothing records which they were.
    conn = op.get_bind()
    role_ids, permission_ids = _ids(conn, roles), _ids(conn, permissions)
    for role, granted in GRANTS.items():
        op.execute(
            role_permissions.delete().where(
                role_permissions.c.role_id == role_ids[role],
                role_permissions.c.permission_id.in_([permission_ids[p] for p in granted]),
            )
        )
    op.execute(permissions.delete().where(permissions.c.name == MANAGE[0]))
