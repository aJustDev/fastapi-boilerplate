"""Development data: an admin user and 50 sample items.

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

import app.models as _models  # noqa: E402, F401
from app.core.config import settings  # noqa: E402
from app.core.db import async_session_factory, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.auth.role import RoleORM  # noqa: E402
from app.models.auth.user import UserORM  # noqa: E402
from app.models.items.item import ItemORM  # noqa: E402

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"  # noqa: S105 -- local development only
CATEGORIES = ["electronics", "furniture", "books", "clothing", "sports"]


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
            ItemORM(
                name=f"Item {i:03d}",
                description=f"Description for item {i}",
                category=CATEGORIES[i % len(CATEGORIES)],
                priority=(i * 7) % 5,
                is_active=i % 7 != 0,
                owner_id=admin.id,
                created_at=now - timedelta(hours=50 - i),
            )
            for i in range(1, 51)
        )
        await session.commit()
        print(f"created {ADMIN_EMAIL} (password: {ADMIN_PASSWORD}) and 50 items")
    await engine.dispose()


if __name__ == "__main__":
    if settings.ENVIRONMENT != "local":
        raise SystemExit(f"refusing to seed development data in ENVIRONMENT={settings.ENVIRONMENT}")
    asyncio.run(seed())
