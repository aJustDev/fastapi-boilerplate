"""Sessions end by counter, not by timestamp: users.session_version replaces tokens_valid_after.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10

Tokens carry the session version they were issued at. Adding a column with a constant
default does not rewrite the table. Tokens issued before this migration have no version
and are rejected: users log in again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.drop_column("users", "tokens_valid_after")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tokens_valid_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_column("users", "session_version")
