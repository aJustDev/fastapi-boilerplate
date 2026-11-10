"""Workshops and enrollments: tables, permissions and jobs of the example context.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-10

A workshop has a limited number of seats; people enrol, wait when it is full and get the
seat of whoever leaves. The user role may see workshops, organize its own and enrol;
workshops:moderate, for the admin role, reaches the workshops of every organizer.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("workshops:read", "See the workshops that were published"),
    ("workshops:create", "Create workshops and run the ones you organize"),
    ("workshops:enroll", "Enrol in workshops and leave them"),
    ("workshops:moderate", "See and run the workshops of any organizer"),
]
# role -> permissions granted by this migration
GRANTS = {
    "admin": [name for name, _ in PERMISSIONS],
    "user": ["workshops:read", "workshops:create", "workshops:enroll"],
}
JOBS = [
    ("workshop_reminders", "Reminds confirmed attendees a day before a workshop starts", 900),
    ("workshops_finish", "Marks published workshops as finished once they end", 300),
]

roles = sa.table("roles", sa.column("id", sa.BigInteger), sa.column("name"))
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


def _audit_columns() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "workshops",
        sa.Column("organizer_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("seats_taken", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.Text(), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_workshops_ends_after_start")),
        sa.CheckConstraint("capacity >= 1", name=op.f("ck_workshops_capacity_positive")),
        sa.CheckConstraint(
            "seats_taken >= 0 AND seats_taken <= capacity",
            name=op.f("ck_workshops_seats_within_capacity"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'cancelled', 'finished')",
            name=op.f("ck_workshops_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organizer_id"],
            ["users.id"],
            name=op.f("fk_workshops_organizer_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workshops")),
    )
    op.create_index(op.f("ix_workshops_organizer_id"), "workshops", ["organizer_id"])
    op.create_index("ix_workshops_starts_at_id", "workshops", ["starts_at", "id"])
    op.create_index(
        "ix_workshops_ends_at_published",
        "workshops",
        ["ends_at"],
        postgresql_where=sa.text("status = 'published'"),
    )

    op.create_table(
        "enrollments",
        sa.Column("workshop_id", sa.BigInteger(), nullable=False),
        sa.Column("attendee_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint(
            "status IN ('confirmed', 'waitlisted', 'cancelled', 'attended', 'no_show')",
            name=op.f("ck_enrollments_status"),
        ),
        sa.ForeignKeyConstraint(
            ["attendee_id"],
            ["users.id"],
            name=op.f("fk_enrollments_attendee_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workshop_id"],
            ["workshops.id"],
            name=op.f("fk_enrollments_workshop_id_workshops"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_enrollments")),
    )
    op.create_index(op.f("ix_enrollments_attendee_id"), "enrollments", ["attendee_id"])
    op.create_index(op.f("ix_enrollments_workshop_id"), "enrollments", ["workshop_id"])
    op.create_index(
        "uq_enrollments_workshop_id_attendee_id_current",
        "enrollments",
        ["workshop_id", "attendee_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )

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
    op.bulk_insert(
        scheduled_jobs,
        [{"job_name": n, "description": d, "interval_seconds": i} for n, d, i in JOBS],
    )


def downgrade() -> None:
    op.execute(
        scheduled_jobs.delete().where(scheduled_jobs.c.job_name.in_([n for n, _, _ in JOBS]))
    )
    # role_permissions rows go with their permission (ON DELETE CASCADE).
    op.execute(permissions.delete().where(permissions.c.name.in_([n for n, _ in PERMISSIONS])))
    op.drop_table("enrollments")
    op.drop_table("workshops")
