"""The states of a workshop and what each one allows."""

from datetime import timedelta

import pytest

from app.workshops.exceptions import EnrollmentClosedError, WorkshopRuleError
from app.workshops.schemas.workshop import WorkshopStatus
from app.workshops.services.lifecycle import (
    ensure_editable,
    ensure_open_for_enrollment,
    ensure_started,
    move_to,
)
from tests._workshops import workshop

DRAFT, PUBLISHED, CANCELLED, FINISHED = WorkshopStatus
ALLOWED = {(DRAFT, PUBLISHED), (DRAFT, CANCELLED), (PUBLISHED, CANCELLED), (PUBLISHED, FINISHED)}
EVERY_PAIR = [(a, b) for a in WorkshopStatus for b in WorkshopStatus]
STARTED = timedelta(hours=-1)


@pytest.mark.parametrize(("current", "target"), EVERY_PAIR)
def test_only_the_transitions_of_the_diagram_happen(current, target):
    w = workshop(status=current)

    if (current, target) in ALLOWED:
        move_to(w, target)
        assert w.status == target
    else:
        with pytest.raises(WorkshopRuleError) as refused:
            move_to(w, target)
        assert refused.value.code == "invalid_state"
        assert w.status == current


@pytest.mark.parametrize(
    ("status", "editable"),
    [(DRAFT, True), (PUBLISHED, True), (CANCELLED, False), (FINISHED, False)],
)
def test_a_workshop_is_editable_until_it_ends_or_is_cancelled(status, editable: bool):
    w = workshop(status=status)

    if editable:
        ensure_editable(w)
    else:
        with pytest.raises(WorkshopRuleError):
            ensure_editable(w)


def test_enrollment_is_open_while_published_and_not_started():
    ensure_open_for_enrollment(workshop())


@pytest.mark.parametrize(
    "closed",
    [
        {"status": DRAFT},
        {"status": CANCELLED},
        {"status": FINISHED},
        {"starts_in": STARTED},
    ],
    ids=["draft", "cancelled", "finished", "already-started"],
)
def test_enrollment_is_closed_otherwise(closed: dict):
    with pytest.raises(EnrollmentClosedError) as refused:
        ensure_open_for_enrollment(workshop(**closed))

    assert refused.value.code == "enrollment_closed"
    assert refused.value.status_code == 409


@pytest.mark.parametrize(
    ("state", "started"),
    [
        ({"starts_in": STARTED}, True),
        ({"status": FINISHED}, True),
        ({}, False),  # published, in a week
        ({"status": DRAFT, "starts_in": STARTED}, False),
        ({"status": CANCELLED, "starts_in": STARTED}, False),
    ],
    ids=["in-progress", "finished", "not-yet", "draft", "cancelled"],
)
def test_attendance_needs_a_workshop_that_took_place(state: dict, started: bool):
    w = workshop(**state)

    if started:
        ensure_started(w)
    else:
        with pytest.raises(WorkshopRuleError):
            ensure_started(w)
