"""The example webhook handler: a delivery that was not accepted is a failure."""

import json
import uuid

import httpx
import pytest

from app.items.event_handlers import item_events

EVENT_ID = uuid.uuid4()


@pytest.fixture
def receiver(monkeypatch: pytest.MonkeyPatch):
    """A fake webhook receiver; set `.status` to choose its answer, read `.requests`."""

    class Receiver:
        status = 200
        requests: list[httpx.Request] = []

        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(self.status)

    fake = Receiver()
    fake.requests = []
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        item_events.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(fake), **kwargs),
    )
    monkeypatch.setattr(item_events.settings, "WEBHOOK_URL", "https://hooks.example.com/items")
    return fake


@pytest.mark.parametrize("status", [400, 404, 500, 503])
async def test_an_answer_that_is_not_a_success_raises(receiver, status: int):
    # Returning would mark the handler as done and the outbox would never retry it.
    receiver.status = status

    with pytest.raises(httpx.HTTPStatusError):
        await item_events.webhook_item_created({"item_id": 1}, EVENT_ID)


async def test_a_delivery_carries_the_event_and_its_id(receiver):
    await item_events.webhook_item_updated({"item_id": 1, "changes": ["name"]}, EVENT_ID)

    (request,) = receiver.requests
    assert request.headers["Idempotency-Key"] == str(EVENT_ID)
    assert json.loads(request.content) == {
        "event": "item.updated",
        "id": str(EVENT_ID),
        "payload": {"item_id": 1, "changes": ["name"]},
    }


async def test_without_a_url_nothing_is_sent(receiver, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(item_events.settings, "WEBHOOK_URL", "")

    await item_events.webhook_item_deleted({"item_id": 1}, EVENT_ID)

    assert receiver.requests == []
