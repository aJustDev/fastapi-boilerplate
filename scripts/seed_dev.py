"""Development data: an admin user and a few workshops to click around with.

Usage: uv run python scripts/seed_dev.py   (after `uv run alembic upgrade head`)

Reference data every environment needs (roles, permissions, scheduled jobs) comes from
the migrations; this script only adds what a developer wants to click around with.
It refuses to run outside ENVIRONMENT=local and does nothing if the admin exists.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

import app.db_registry as _db_registry  # noqa: E402, F401
from app.auth.models.role import RoleORM  # noqa: E402
from app.auth.models.user import UserORM  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import async_session_factory, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.workshops.models import WorkshopORM  # noqa: E402

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"  # noqa: S105 -- local development only
# (title, starts in days, capacity, status): open ones to enrol in, one of each other state.
WORKSHOPS = [
    ("Intro to pottery", 3, 8, "published"),
    ("Wheel throwing", 7, 2, "published"),
    ("Glazing basics", 14, 12, "published"),
    ("Kiln firing", 0.5, 6, "published"),  # starts within a day: the reminders job picks it
    ("Raku weekend", 30, 10, "draft"),
    ("Hand building", -10, 8, "finished"),
]


async def seed() -> None:
    async with async_session_factory() as session:
        exists = await session.scalar(select(UserORM.id).where(UserORM.email == ADMIN_EMAIL))
        if exists:
            print(f"{ADMIN_EMAIL} already exists, nothing to do")
            return

        admin_role = await session.scalar(select(RoleORM).where(RoleORM.name == "admin"))
        if admin_role is None:
            raise SystemExit("role 'admin' not found: run `uv run alembic upgrade head` first")

        admin = UserORM(
            email=ADMIN_EMAIL,
            username="admin",
            password_hash=hash_password(ADMIN_PASSWORD),
            full_name="Administrator",
            is_active=True,
            roles=[admin_role],
        )
        session.add(admin)
        await session.flush()

        now = datetime.now(UTC)
        session.add_all(
            WorkshopORM(
                organizer_id=admin.id,
                title=title,
                description=f"Sample workshop: {title.lower()}",
                starts_at=now + timedelta(days=days),
                ends_at=now + timedelta(days=days, hours=2),
                capacity=capacity,
                status=status,
            )
            for title, days, capacity, status in WORKSHOPS
        )
        await session.commit()
        print(f"created {ADMIN_EMAIL} (password: {ADMIN_PASSWORD}) and {len(WORKSHOPS)} workshops")
    await engine.dispose()


if __name__ == "__main__":
    if settings.ENVIRONMENT != "local":
        raise SystemExit(f"refusing to seed development data in ENVIRONMENT={settings.ENVIRONMENT}")
    asyncio.run(seed())
