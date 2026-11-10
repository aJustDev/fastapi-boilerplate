"""Schedule the outbox cleanup: a row for the outbox_cleanup job.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-10

Every published event leaves a row in outbox_events. The job deletes the PROCESSED ones
older than OUTBOX_CLEANUP_DAYS once a day.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOB = ("outbox_cleanup", "Deletes processed outbox events past their retention", 86400)

scheduled_jobs = sa.table(
    "scheduled_jobs",
    sa.column("job_name"),
    sa.column("description"),
    sa.column("interval_seconds", sa.Integer),
)


def upgrade() -> None:
    name, description, interval = JOB
    op.bulk_insert(
        scheduled_jobs,
        [{"job_name": name, "description": description, "interval_seconds": interval}],
    )


def downgrade() -> None:
    op.execute(scheduled_jobs.delete().where(scheduled_jobs.c.job_name == JOB[0]))
