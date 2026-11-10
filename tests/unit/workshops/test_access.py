"""Who may see a workshop and who may run it."""

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError
from app.workshops.schemas.workshop import WorkshopStatus
from app.workshops.services.access import ensure_runs, ensure_visible, viewer_filter
from tests._workshops import MODERATOR, ORGANIZER, SOMEONE_ELSE, workshop

AFTER_DRAFT = [s for s in WorkshopStatus if s is not WorkshopStatus.DRAFT]


class TestVisibility:
    @pytest.mark.parametrize("actor", [ORGANIZER, MODERATOR])
    def test_a_draft_exists_for_its_organizer_and_for_a_moderator(self, actor):
        draft = workshop(status=WorkshopStatus.DRAFT)

        assert ensure_visible(draft, draft.id, actor) is draft

    def test_someone_elses_draft_looks_missing(self):
        draft = workshop(status=WorkshopStatus.DRAFT)

        with pytest.raises(NotFoundError) as hidden:
            ensure_visible(draft, draft.id, SOMEONE_ELSE)
        with pytest.raises(NotFoundError) as absent:
            ensure_visible(None, draft.id, SOMEONE_ELSE)

        # The same answer as an id nobody has.
        assert str(hidden.value) == str(absent.value)

    @pytest.mark.parametrize("status", AFTER_DRAFT)
    def test_what_left_draft_is_seen_by_everyone(self, status):
        w = workshop(status=status)

        assert ensure_visible(w, w.id, SOMEONE_ELSE) is w


class TestRunning:
    @pytest.mark.parametrize("actor", [ORGANIZER, MODERATOR])
    def test_the_organizer_and_a_moderator_run_it(self, actor):
        w = workshop()

        assert ensure_runs(w, w.id, actor) is w

    def test_a_public_workshop_of_someone_else_is_forbidden_not_missing(self):
        w = workshop()

        with pytest.raises(AuthorizationError) as refused:
            ensure_runs(w, w.id, SOMEONE_ELSE)

        assert refused.value.status_code == 403

    def test_a_draft_of_someone_else_is_missing_not_forbidden(self):
        draft = workshop(status=WorkshopStatus.DRAFT)

        with pytest.raises(NotFoundError):
            ensure_runs(draft, draft.id, SOMEONE_ELSE)

    def test_nothing_runs_what_does_not_exist(self):
        with pytest.raises(NotFoundError):
            ensure_runs(None, 5, MODERATOR)


def test_a_listing_is_limited_to_the_view_of_the_caller_unless_it_moderates():
    assert viewer_filter(SOMEONE_ELSE) == SOMEONE_ELSE.user_id
    assert viewer_filter(MODERATOR) is None
