from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.security import create_access_token, hash_password
from app.models.auth.user import UserORM
from main import app


@pytest.fixture
def fake_user() -> UserORM:
    user = MagicMock(spec=UserORM)
    user.id = 1
    user.email = "test@example.com"
    user.username = "testuser"
    user.full_name = "Test User"
    user.is_active = True
    user.password_hash = hash_password("testpass123")
    user.roles = []
    user.has_role = MagicMock(return_value=False)
    user.has_permission = MagicMock(return_value=False)
    return user


@pytest.fixture
def auth_headers(fake_user: UserORM) -> dict[str, str]:
    token = create_access_token(subject=str(fake_user.id), scopes=[])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
async def client(mock_session: AsyncMock) -> AsyncGenerator[AsyncClient]:
    async def _override_session() -> AsyncGenerator:
        yield mock_session

    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
