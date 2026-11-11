"""What the workshop rules answer when they refuse an operation.

All of them are 409: the request was well formed and allowed, and the state it met does
not permit it. Each rule a client can react to differently has its own code.
"""

from app.core.events.dispatcher import ExpectedFailure
from app.core.exceptions import UseCaseException


class WorkshopRuleError(UseCaseException):
    """The workshop or the enrollment is not in a state that allows the operation."""

    status_code = 409
    code = "invalid_state"


class EnrollmentClosedError(WorkshopRuleError):
    """Enrolling and leaving are open while the workshop is published and has not started."""

    code = "enrollment_closed"

    def __init__(self) -> None:
        super().__init__("The workshop is not open for enrollment")


class VersionConflictError(WorkshopRuleError):
    """The workshop changed since the client read it."""

    code = "version_conflict"

    def __init__(self, current: int) -> None:
        super().__init__(f"The workshop was changed by someone else (current version: {current})")


class CapacityBelowEnrolledError(WorkshopRuleError):
    code = "capacity_below_enrolled"

    def __init__(self, seats_taken: int) -> None:
        super().__init__(f"Capacity cannot go below the {seats_taken} seats already taken")


class WebhookRejectedError(ExpectedFailure):
    """The webhook answered, and not with a 2xx: the event was not delivered."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"webhook answered {status_code}")


class WebhookUnreachableError(ExpectedFailure):
    """The webhook did not answer: connection refused, timeout, DNS."""
