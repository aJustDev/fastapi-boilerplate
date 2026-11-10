"""WorkshopRepo against PostgreSQL: what a viewer sees, the lock, the finish job's query."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.schemas.workshop import WorkshopStatus

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

DRAFT, PUBLISHED, CANCELLED, FINISHED = WorkshopStatus


@pytest.fixture
def repo(db_session: AsyncSession) -> WorkshopRepo:
    return WorkshopRepo(db_session)


class TestListVisible:
    async def test_a_viewer_sees_what_left_draft_and_its_own_drafts(
        self, repo: WorkshopRepo, users, make_workshop
    ):
        organizer, other, *_ = users
        own_draft = await make_workshop(status=DRAFT)
        others_draft = await make_workshop(status=DRAFT, organizer_id=other.id)
        public = [await make_workshop(status=s) for s in (PUBLISHED, CANCELLED, FINISHED)]

        seen, _, _ = await repo.list_visible(organizer.id)

        assert {w.id for w in seen} == {own_draft.id, *(w.id for w in public)}
        assert others_draft.id not in {w.id for w in seen}

    async def test_no_viewer_means_no_restriction(self, repo: WorkshopRepo, users, make_workshop):
        drafts = [await make_workshop(status=DRAFT, organizer_id=u.id) for u in users[:3]]

        seen, _, _ = await repo.list_visible(None)

        assert {w.id for w in seen} == {w.id for w in drafts}

    async def test_filters_apply_inside_what_is_visible(
        self, repo: WorkshopRepo, users, make_workshop
    ):
        organizer, other, *_ = users
        await make_workshop(status=DRAFT, organizer_id=other.id, title="Secret glazing")
        soon = await make_workshop(title="Glazing basics", starts_in=timedelta(days=1))
        later = await make_workshop(title="Wheel throwing", starts_in=timedelta(days=30))

        by_title, _, _ = await repo.list_visible(organizer.id, filters={"title": "glazing"})
        by_status, _, _ = await repo.list_visible(organizer.id, filters={"status": DRAFT})
        by_date, _, _ = await repo.list_visible(
            organizer.id, filters={"starts_after": soon.starts_at + timedelta(days=1)}
        )

        assert [w.id for w in by_title] == [soon.id]
        assert by_status == []
        assert [w.id for w in by_date] == [later.id]

    async def test_pages_follow_the_start_date_with_the_id_breaking_ties(
        self, repo: WorkshopRepo, users, make_workshop
    ):
        first = await make_workshop(starts_in=timedelta(days=2))
        same_start = [
            await make_workshop(starts_at=first.starts_at, ends_at=first.ends_at) for _ in range(3)
        ]
        earlier = await make_workshop(starts_in=timedelta(days=1))
        expected = [earlier.id, first.id, *(w.id for w in same_start)]

        seen, cursor = [], None
        for _ in range(6):
            page, cursor, has_more = await repo.list_visible(
                users[0].id, cursor=cursor, limit=2, order_by="starts_at"
            )
            seen.extend(w.id for w in page)
            if not has_more:
                break

        assert seen == expected


class TestGetForUpdate:
    async def test_returns_what_is_stored_now_not_what_the_session_remembers(
        self, repo: WorkshopRepo, db_session: AsyncSession, make_workshop
    ):
        workshop = await make_workshop()
        # Another statement changed the row behind the session's copy.
        await db_session.execute(
            text("UPDATE workshops SET seats_taken = 2 WHERE id = :id"), {"id": workshop.id}
        )
        assert workshop.seats_taken == 0

        locked = await repo.get_for_update(workshop.id)

        assert locked is workshop
        assert locked.seats_taken == 2

    async def test_of_nothing_is_none(self, repo: WorkshopRepo):
        assert await repo.get_for_update(999_999) is None


class TestFinishEnded:
    async def test_only_published_workshops_past_their_end_finish(
        self, repo: WorkshopRepo, db_session: AsyncSession, make_workshop
    ):
        long_ago = timedelta(days=-2)
        ended = await make_workshop(starts_in=long_ago)
        in_progress = await make_workshop(starts_in=timedelta(hours=-1))  # ends an hour from now
        upcoming = await make_workshop()
        ended_draft = await make_workshop(starts_in=long_ago, status=DRAFT)
        ended_cancelled = await make_workshop(starts_in=long_ago, status=CANCELLED)

        finished = await repo.finish_ended()

        assert finished == 1
        for workshop in (ended, in_progress, upcoming, ended_draft, ended_cancelled):
            await db_session.refresh(workshop)
        assert ended.status == FINISHED
        assert [w.status for w in (in_progress, upcoming)] == [PUBLISHED, PUBLISHED]
        assert (ended_draft.status, ended_cancelled.status) == (DRAFT, CANCELLED)
        assert await repo.finish_ended() == 0


class TestConstraints:
    """The last line of defence: what the database refuses whatever the code does."""

    @pytest.mark.parametrize(
        "impossible",
        [
            {"seats_taken": 4},  # capacity is 3
            {"seats_taken": -1},
            {"capacity": 0},
            {"status": "postponed"},
            {"ends_at": datetime(2000, 1, 1, tzinfo=UTC)},
        ],
        ids=["overbooked", "negative-seats", "no-capacity", "unknown-status", "ends-before-start"],
    )
    async def test_an_impossible_workshop_is_not_stored(
        self, db_session: AsyncSession, make_workshop, impossible: dict
    ):
        with pytest.raises(IntegrityError):
            await make_workshop(**impossible)
        await db_session.rollback()
