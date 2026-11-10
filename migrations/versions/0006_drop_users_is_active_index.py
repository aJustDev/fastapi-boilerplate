"""Drop ix_users_is_active: a partial index on the value almost every row has.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-10

`WHERE is_active = true` covers nearly the whole table, so the planner never prefers it to
a sequential scan and every write to users pays for keeping it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_users_is_active", table_name="users")


def downgrade() -> None:
    op.create_index(
        "ix_users_is_active",
        "users",
        ["is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
