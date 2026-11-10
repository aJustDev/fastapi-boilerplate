"""Requests that arrive together, each on its own connection to a real PostgreSQL.

What must hold however they interleave: a workshop never has more people seated than
seats, its counter says how many are seated, and nobody waits while a seat is free. The
lock that makes it hold is in app/workshops/services/seating.py.
"""

import asyncio

import pytest
from httpx import AsyncClient

from tests.integration.api.helpers import signed_up
from tests.integration.api.workshops import (
    create_workshop,
    enroll,
    events,
    get_workshop,
    published_workshop,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

PEOPLE = 8


async def _crowd(client: AsyncClient, count: int = PEOPLE) -> list[dict[str, str]]:
    return [await signed_up(client, f"person{n}") for n in range(count)]


async def _seating(client: AsyncClient, organizer: dict[str, str], workshop_id: int) -> list[str]:
    """Enrollment statuses of the workshop, after checking that its seats add up."""
    workshop = await get_workshop(client, organizer, workshop_id)
    listed = await client.get(
        f"/v1/workshops/{workshop_id}/enrollments", params={"page_size": 100}, headers=organizer
    )
    statuses = [e["status"] for e in listed.json()["items"]]

    seated = statuses.count("confirmed")
    assert seated <= workshop["capacity"], f"overbooked: {statuses}"
    assert workshop["seats_taken"] == seated, f"counter says {workshop['seats_taken']}: {statuses}"
    if "waitlisted" in statuses and workshop["status"] == "published":
        assert seated == workshop["capacity"], f"a seat is free with people waiting: {statuses}"
    return statuses


@pytest.mark.parametrize("capacity", [1, 3])
async def test_enrolling_at_once_never_seats_more_people_than_seats(
    api_client: AsyncClient, capacity: int
):
    organizer = await signed_up(api_client, "organizer")
    crowd = await _crowd(api_client)
    workshop = await published_workshop(api_client, organizer, capacity=capacity)

    answers = await asyncio.gather(*(enroll(api_client, who, workshop["id"]) for who in crowd))

    assert [a.status_code for a in answers] == [201] * PEOPLE
    statuses = await _seating(api_client, organizer, workshop["id"])
    assert statuses.count("confirmed") == capacity
    assert statuses.count("waitlisted") == PEOPLE - capacity
    assert len(await events("enrollment.confirmed")) == capacity


async def test_the_same_user_enrolling_at_once_gets_one_enrollment(api_client: AsyncClient):
    organizer = await signed_up(api_client, "organizer")
    ana = await signed_up(api_client, "ana")
    workshop = await published_workshop(api_client, organizer, capacity=5)

    answers = await asyncio.gather(*(enroll(api_client, ana, workshop["id"]) for _ in range(6)))

    assert sorted(a.status_code for a in answers) == [200] * 5 + [201]
    assert len({a.json()["id"] for a in answers}) == 1
    assert await _seating(api_client, organizer, workshop["id"]) == ["confirmed"]
    assert len(await events("enrollment.confirmed")) == 1


async def test_leaving_and_enrolling_at_once_leaves_no_seat_free_with_people_waiting(
    api_client: AsyncClient,
):
    organizer = await signed_up(api_client, "organizer")
    crowd = await _crowd(api_client, 10)
    seated, arriving = crowd[:4], crowd[4:]
    workshop = await published_workshop(api_client, organizer, capacity=4)
    for who in seated:
        await enroll(api_client, who, workshop["id"])
    url = f"/v1/workshops/{workshop['id']}/enrollments/me"

    answers = await asyncio.gather(
        *(api_client.delete(url, headers=who) for who in seated),
        *(enroll(api_client, who, workshop["id"]) for who in arriving),
    )

    assert [a.status_code for a in answers] == [204] * 4 + [201] * 6
    statuses = await _seating(api_client, organizer, workshop["id"])
    # Four left and six came: the four seats are taken again and two people wait.
    assert sorted(statuses) == ["cancelled"] * 4 + ["confirmed"] * 4 + ["waitlisted"] * 2


async def test_edits_from_the_same_version_are_applied_once(api_client: AsyncClient):
    organizer = await signed_up(api_client, "organizer")
    workshop = await create_workshop(api_client, organizer)
    url = f"/v1/workshops/{workshop['id']}"

    answers = await asyncio.gather(
        *(
            api_client.patch(url, json={"version": 1, "title": f"edit {n}"}, headers=organizer)
            for n in range(6)
        )
    )

    assert sorted(a.status_code for a in answers) == [200] + [409] * 5
    assert {a.json()["code"] for a in answers if a.status_code == 409} == {"version_conflict"}
    (applied,) = [a.json() for a in answers if a.status_code == 200]
    stored = await get_workshop(api_client, organizer, workshop["id"])
    assert (stored["title"], stored["version"]) == (applied["title"], 2)


async def test_cancelling_while_people_enrol_leaves_nobody_enrolled(api_client: AsyncClient):
    organizer = await signed_up(api_client, "organizer")
    crowd = await _crowd(api_client)
    workshop = await published_workshop(api_client, organizer, capacity=3)

    cancelled, *answers = await asyncio.gather(
        api_client.post(f"/v1/workshops/{workshop['id']}/cancel", headers=organizer),
        *(enroll(api_client, who, workshop["id"]) for who in crowd),
    )

    assert cancelled.status_code == 200
    # Whoever got in before the cancellation was cancelled with it; the rest were refused.
    assert {a.status_code for a in answers} <= {201, 409}
    statuses = await _seating(api_client, organizer, workshop["id"])
    assert set(statuses) <= {"cancelled"}
    assert len(statuses) == [a.status_code for a in answers].count(201)
    told = await events("enrollment.cancelled")
    assert len(told) == len(statuses)
