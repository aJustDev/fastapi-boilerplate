"""outbox_events.aggregate_id and correlation_id become text.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10

They were UUID columns that nothing could fill: the ids of this code base are BIGINT and
the correlation id is the request id, a token of up to 64 characters. Changing the type
rewrites the table under an exclusive lock; on a large outbox, run it in a quiet moment.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("aggregate_id", "correlation_id")
_UUID = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def upgrade() -> None:
    for column in COLUMNS:
        op.alter_column(
            "outbox_events",
            column,
            existing_type=sa.UUID(),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Values that are not UUIDs (entity ids, request ids) cannot go back: they become NULL.
    for column in COLUMNS:
        op.alter_column(
            "outbox_events",
            column,
            existing_type=sa.Text(),
            type_=sa.UUID(),
            existing_nullable=True,
            postgresql_using=f"CASE WHEN {column} ~ '{_UUID}' THEN {column}::uuid END",
        )
