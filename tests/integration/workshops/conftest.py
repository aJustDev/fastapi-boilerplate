from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models.user import UserORM
from app.workshops.models import EnrollmentORM, WorkshopORM
from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.schemas.workshop import WorkshopStatus


@pytest_asyncio.fixture(loop_scope="session")
async def users(db_session: AsyncSession) -> list[UserORM]:
    """Five accounts: the first organizes, the others enrol."""
    created = [
        UserORM(email=f"user{n}@example.com", username=f"user{n}", password_hash="x")
        for n in range(5)
    ]
    db_session.add_all(created)
    await db_session.flush()
    return created


@pytest.fixture
def make_workshop(db_session: AsyncSession, users: list[UserORM]):
    """Store a workshop of the first user: published, in a week, unless told otherwise."""

    async def _make(*, starts_in: timedelta = timedelta(days=7), **overrides: Any) -> WorkshopORM:
        starts_at = datetime.now(UTC) + starts_in
        values: dict[str, Any] = {
            "organizer_id": users[0].id,
            "title": "Intro to pottery",
            "starts_at": starts_at,
            "ends_at": starts_at + timedelta(hours=2),
            "capacity": 3,
            "status": WorkshopStatus.PUBLISHED,
        }
        workshop = WorkshopORM(**values | overrides)
        db_session.add(workshop)
        await db_session.flush()
        return workshop

    return _make


@pytest.fixture
def make_enrollment(db_session: AsyncSession):
    async def _make(
        workshop: WorkshopORM,
        attendee: UserORM,
        status: EnrollmentStatus = EnrollmentStatus.CONFIRMED,
        **overrides: Any,
    ) -> EnrollmentORM:
        enrollment = EnrollmentORM(
            workshop_id=workshop.id, attendee_id=attendee.id, status=status, **overrides
        )
        db_session.add(enrollment)
        await db_session.flush()
        return enrollment

    return _make
