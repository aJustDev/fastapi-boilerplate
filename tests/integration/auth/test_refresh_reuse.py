"""A replayed refresh token ends every session, even though its request fails."""

import pytest
from sqlalchemy import select

from app.auth.models.user import UserORM
from app.auth.repos.revoked_token import RevokedTokenRepo
from app.auth.repos.user import UserRepo
from app.auth.services.auth import AuthService
from app.auth.use_cases import refresh_token as refresh_module
from app.auth.use_cases.refresh_token import RefreshTokenUseCase
from app.core.exceptions import RefreshTokenReuseError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture
def committing_tables() -> list[str]:
    return ["revoked_tokens", "users"]


async def test_reuse_invalidation_survives_the_request_rollback(committing_factory, monkeypatch):
    monkeypatch.setattr(refresh_module, "async_session_factory", committing_factory)
    async with committing_factory() as session:
        user = UserORM(
            email="victim@test.com",
            username="victim",
            password_hash=hash_password("TestPass123!"),
            is_active=True,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    async def refresh_in_a_request(token: str):
        # Like get_session: commit on success, rollback on error.
        async with committing_factory() as session:
            service = AuthService(UserRepo(session), RevokedTokenRepo(session))
            try:
                result = await RefreshTokenUseCase(service).execute(token)
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            return result

    stolen = create_refresh_token(subject=str(user_id))
    access_before = create_access_token(subject=str(user_id))

    rotated = await refresh_in_a_request(stolen)  # legitimate rotation
    with pytest.raises(RefreshTokenReuseError):
        await refresh_in_a_request(stolen)  # replay

    async with committing_factory() as session:
        reloaded = (
            await session.execute(select(UserORM).where(UserORM.id == user_id))
        ).scalar_one()
    # Committed although the replaying request was rolled back, and it ends the pair
    # issued a moment ago as well as the older one.
    assert reloaded.session_version == 1
    assert not reloaded.accepts_session(decode_token(access_before)["sv"])
    assert not reloaded.accepts_session(decode_token(rotated.refresh_token)["sv"])
