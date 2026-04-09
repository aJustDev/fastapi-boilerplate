import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.auth.permission import PermissionORM
from app.models.auth.role import RoleORM
from app.models.auth.user import UserORM
from app.repos.auth.user import UserRepo

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture
def repo(db_session: AsyncSession) -> UserRepo:
    return UserRepo(db_session)


def _make_user(email: str = "user@test.com", username: str = "testuser") -> UserORM:
    return UserORM(
        email=email,
        username=username,
        password_hash=hash_password("TestPass123!"),
        full_name="Test User",
        is_active=True,
    )


# -- CRUD -----------------------------------------------------------------


class TestCreate:
    async def test_create_user(self, repo: UserRepo):
        user = _make_user()
        created = await repo.create(user)

        assert created.id is not None
        assert created.email == "user@test.com"
        assert created.username == "testuser"
        assert created.created_at is not None

    async def test_duplicate_email_raises(self, repo: UserRepo):
        await repo.create(_make_user(email="dup@test.com", username="user1"))

        with pytest.raises(IntegrityError):
            await repo.create(_make_user(email="dup@test.com", username="user2"))

    async def test_duplicate_username_raises(self, repo: UserRepo):
        await repo.create(_make_user(email="a@test.com", username="dupuser"))

        with pytest.raises(IntegrityError):
            await repo.create(_make_user(email="b@test.com", username="dupuser"))


class TestGetById:
    async def test_get_existing_user(self, repo: UserRepo):
        created = await repo.create(_make_user())

        found = await repo.get_by_id(created.id)

        assert found is not None
        assert found.id == created.id
        assert found.email == "user@test.com"

    async def test_get_nonexistent_user(self, repo: UserRepo):
        found = await repo.get_by_id(999999)
        assert found is None


# -- Custom queries -------------------------------------------------------


class TestGetByEmail:
    async def test_found(self, repo: UserRepo):
        await repo.create(_make_user(email="find@test.com", username="findme"))

        found = await repo.get_by_email("find@test.com")

        assert found is not None
        assert found.email == "find@test.com"

    async def test_not_found(self, repo: UserRepo):
        found = await repo.get_by_email("nonexistent@test.com")
        assert found is None


class TestGetByUsername:
    async def test_found(self, repo: UserRepo):
        await repo.create(_make_user(email="byname@test.com", username="findbyname"))

        found = await repo.get_by_username("findbyname")

        assert found is not None
        assert found.username == "findbyname"

    async def test_not_found(self, repo: UserRepo):
        found = await repo.get_by_username("ghostuser")
        assert found is None


# -- Relationships --------------------------------------------------------


class TestRolesRelationship:
    async def test_user_loads_roles(self, db_session: AsyncSession):
        role = RoleORM(name="admin", description="Admin role")
        db_session.add(role)
        await db_session.flush()
        await db_session.refresh(role)

        user = _make_user(email="withrole@test.com", username="roleuser")
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        # Assign role via association table
        from app.models.auth.associations import user_roles

        await db_session.execute(user_roles.insert().values(user_id=user.id, role_id=role.id))
        await db_session.flush()

        # Expire cached state so selectinload re-fetches relationships
        db_session.expire(user)

        repo = UserRepo(db_session)
        loaded = await repo.get_by_email("withrole@test.com")

        assert loaded is not None
        assert len(loaded.roles) == 1
        assert loaded.roles[0].name == "admin"
        assert loaded.has_role("admin") is True
        assert loaded.has_role("editor") is False

    async def test_user_loads_permissions_through_roles(self, db_session: AsyncSession):
        perm = PermissionORM(name="items:write", description="Write items")
        db_session.add(perm)
        await db_session.flush()
        await db_session.refresh(perm)

        role = RoleORM(name="editor", description="Editor role")
        db_session.add(role)
        await db_session.flush()
        await db_session.refresh(role)

        from app.models.auth.associations import role_permissions

        await db_session.execute(
            role_permissions.insert().values(role_id=role.id, permission_id=perm.id)
        )
        await db_session.flush()

        user = _make_user(email="withperm@test.com", username="permuser")
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)

        from app.models.auth.associations import user_roles

        await db_session.execute(user_roles.insert().values(user_id=user.id, role_id=role.id))
        await db_session.flush()

        # Expire cached state so selectinload re-fetches relationships
        db_session.expire(user)
        db_session.expire(role)

        repo = UserRepo(db_session)
        loaded = await repo.get_by_email("withperm@test.com")

        assert loaded is not None
        assert loaded.has_permission("items:write") is True
        assert loaded.has_permission("items:delete") is False


# -- Update & Delete ------------------------------------------------------


class TestUpdateUser:
    async def test_update_fields(self, repo: UserRepo):
        created = await repo.create(_make_user())

        updated = await repo.update(created, {"full_name": "New Name", "is_active": False})

        assert updated.full_name == "New Name"
        assert updated.is_active is False


class TestDeleteUser:
    async def test_delete_user(self, repo: UserRepo):
        created = await repo.create(_make_user())

        await repo.delete(created)

        found = await repo.get_by_id(created.id)
        assert found is None
