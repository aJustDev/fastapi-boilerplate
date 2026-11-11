"""The webhook handlers: a delivery that was not accepted is a failure."""

import json
import uuid

import httpx
import pytest

from app.core.events.dispatcher import ExpectedFailure
from app.workshops.event_handlers import notifications
from app.workshops.exceptions import WebhookRejectedError, WebhookUnreachableError

EVENT_ID = uuid.uuid4()
PAYLOAD = {"enrollment_id": 1, "workshop_id": 2, "attendee_id": 3}
HANDLERS = {
    "enrollment.confirmed": notifications.notify_confirmed,
    "enrollment.promoted": notifications.notify_promoted,
    "enrollment.cancelled": notifications.notify_cancelled,
    "enrollment.reminder": notifications.notify_reminder,
}


@pytest.fixture
def receiver(monkeypatch: pytest.MonkeyPatch):
    """A fake webhook receiver; set `.status` to choose its answer, read `.requests`."""

    class Receiver:
        status = 200
        requests: list[httpx.Request]

        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(self.status)

    fake = Receiver()
    fake.requests = []
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        notifications.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(fake), **kwargs),
    )
    monkeypatch.setattr(notifications.settings, "WEBHOOK_URL", "https://hooks.example.com/in")
    return fake


@pytest.mark.parametrize("status", [301, 400, 404, 500, 503])
async def test_an_answer_that_is_not_a_success_raises(receiver, status: int):
    # Returning would mark the handler as done and the outbox would never retry it.
    receiver.status = status

    with pytest.raises(WebhookRejectedError) as rejected:
        await notifications.notify_confirmed(PAYLOAD, EVENT_ID)

    # httpx's own error names the URL, and a webhook URL is often a secret: it would land
    # in every retry line and in the stored error.
    assert str(rejected.value) == f"webhook answered {status}"
    assert "hooks.example.com" not in str(rejected.value)


async def test_a_receiver_that_does_not_answer_raises_without_the_url(monkeypatch):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[Errno 111] Connection refused", request=request)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        notifications.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(refuse), **kwargs),
    )
    monkeypatch.setattr(notifications.settings, "WEBHOOK_URL", "https://hooks.example.com/t0k3n")

    with pytest.raises(WebhookUnreachableError) as unreachable:
        await notifications.notify_confirmed(PAYLOAD, EVENT_ID)

    assert str(unreachable.value) == "ConnectError: [Errno 111] Connection refused"
    assert isinstance(unreachable.value, ExpectedFailure)


@pytest.mark.parametrize("event_type", HANDLERS)
async def test_a_delivery_carries_the_event_and_its_id(receiver, event_type: str):
    await HANDLERS[event_type](PAYLOAD, EVENT_ID)

    (request,) = receiver.requests
    assert request.headers["Idempotency-Key"] == str(EVENT_ID)
    assert json.loads(request.content) == {
        "event": event_type,
        "id": str(EVENT_ID),
        "payload": PAYLOAD,
    }


async def test_without_a_url_nothing_is_sent(receiver, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(notifications.settings, "WEBHOOK_URL", "")

    await notifications.notify_cancelled(PAYLOAD, EVENT_ID)

    assert receiver.requests == []
