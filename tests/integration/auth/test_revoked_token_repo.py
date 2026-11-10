import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repos.revoked_token import RevokedTokenRepo

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture
def repo(db_session: AsyncSession) -> RevokedTokenRepo:
    return RevokedTokenRepo(db_session)


async def test_revoking_twice_reports_the_second_as_already_revoked(repo: RevokedTokenRepo):
    jti = uuid.uuid4()
    expires = datetime.now(UTC) + timedelta(days=1)

    assert await repo.revoke(jti, expires) is True
    assert await repo.revoke(jti, expires) is False
    assert await repo.is_revoked(jti)


async def test_delete_expired_keeps_live_revocations(repo: RevokedTokenRepo):
    now = datetime.now(UTC)
    expired, live = uuid.uuid4(), uuid.uuid4()
    await repo.revoke(expired, now - timedelta(minutes=1))
    await repo.revoke(live, now + timedelta(minutes=1))

    assert await repo.delete_expired() >= 1
    assert not await repo.is_revoked(expired)
    assert await repo.is_revoked(live)
