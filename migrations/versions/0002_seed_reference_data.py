"""Reference data every environment needs: roles, permissions and scheduled jobs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10

Development-only data (the admin user and sample items) lives in scripts/seed_dev.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = [
    ("admin", "Full system access"),
    ("user", "Standard user access"),
]
PERMISSIONS = [
    ("users:read", "View user information"),
    ("users:write", "Create and modify users"),
    ("items:read", "View items"),
    ("items:write", "Create and modify items"),
    ("items:delete", "Delete items"),
]
# role -> permissions; admin gets every permission.
ROLE_PERMISSIONS = {
    "admin": [name for name, _ in PERMISSIONS],
    "user": ["users:read", "items:read", "items:write"],
}
JOBS = [
    ("heartbeat_check", "Example job: logs worker identity every 5 minutes", 300),
    ("revoked_tokens_cleanup", "Deletes revocations of expired tokens", 3600),
]

roles = sa.table(
    "roles", sa.column("id", sa.BigInteger), sa.column("name"), sa.column("description")
)
permissions = sa.table(
    "permissions", sa.column("id", sa.BigInteger), sa.column("name"), sa.column("description")
)
role_permissions = sa.table(
    "role_permissions",
    sa.column("role_id", sa.BigInteger),
    sa.column("permission_id", sa.BigInteger),
)
scheduled_jobs = sa.table(
    "scheduled_jobs",
    sa.column("job_name"),
    sa.column("description"),
    sa.column("interval_seconds", sa.Integer),
)


def upgrade() -> None:
    op.bulk_insert(roles, [{"name": n, "description": d} for n, d in ROLES])
    op.bulk_insert(permissions, [{"name": n, "description": d} for n, d in PERMISSIONS])

    conn = op.get_bind()
    role_ids = dict(conn.execute(sa.select(roles.c.name, roles.c.id)).all())
    permission_ids = dict(conn.execute(sa.select(permissions.c.name, permissions.c.id)).all())
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_ids[role], "permission_id": permission_ids[permission]}
            for role, granted in ROLE_PERMISSIONS.items()
            for permission in granted
        ],
    )

    op.bulk_insert(
        scheduled_jobs,
        [{"job_name": n, "description": d, "interval_seconds": i} for n, d, i in JOBS],
    )


def downgrade() -> None:
    op.execute(
        scheduled_jobs.delete().where(scheduled_jobs.c.job_name.in_([n for n, _, _ in JOBS]))
    )
    op.execute(roles.delete().where(roles.c.name.in_([n for n, _ in ROLES])))
    op.execute(permissions.delete().where(permissions.c.name.in_([n for n, _ in PERMISSIONS])))
