"""What the request schemas let through, and that the stored values match the enums."""

import re

import pytest
from pydantic import ValidationError

from app.workshops.models import EnrollmentORM, WorkshopORM
from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.schemas.workshop import WorkshopCreate, WorkshopStatus, WorkshopUpdate
from tests._workshops import workshop_body


class TestWorkshopCreate:
    def test_accepts_a_valid_workshop(self):
        created = WorkshopCreate.model_validate(workshop_body(title="  Pottery  "))

        assert created.title == "Pottery"
        assert created.ends_at > created.starts_at

    @pytest.mark.parametrize(
        "overrides",
        [
            {"capacity": 0},
            {"capacity": 10_001},
            {"title": ""},
            {"title": "x" * 201},
            {"title": "a\x00b"},
            {"description": "x" * 10_001},
            {"starts_at": "2030-05-04T10:00:00"},
            {"starts_at": "0001-01-01T00:00:00+14:00"},
            {"ends_at": "1990-01-01T00:00:00Z"},
        ],
        ids=[
            "no-seats",
            "too-many-seats",
            "empty-title",
            "title-too-long",
            "nul-in-title",
            "description-too-long",
            "start-without-offset",
            "start-out-of-range",
            "ends-before-it-starts",
        ],
    )
    def test_rejects(self, overrides: dict):
        with pytest.raises(ValidationError):
            WorkshopCreate.model_validate(workshop_body(**overrides))

    def test_a_workshop_cannot_end_when_it_starts(self):
        body = workshop_body()

        with pytest.raises(ValidationError, match="ends_at must be after starts_at"):
            WorkshopCreate.model_validate(body | {"ends_at": body["starts_at"]})


class TestWorkshopUpdate:
    def test_the_version_is_required(self):
        with pytest.raises(ValidationError):
            WorkshopUpdate.model_validate({"title": "New"})

    def test_only_what_was_sent_counts_as_a_change(self):
        update = WorkshopUpdate.model_validate({"version": 1, "capacity": 5})

        assert update.model_dump(exclude_unset=True, exclude={"version"}) == {"capacity": 5}

    @pytest.mark.parametrize("field", ["title", "starts_at", "ends_at", "capacity"])
    def test_null_is_refused_for_what_cannot_be_empty(self, field: str):
        with pytest.raises(ValidationError, match="null is not allowed"):
            WorkshopUpdate.model_validate({"version": 1, field: None})

    def test_null_clears_the_description(self):
        update = WorkshopUpdate.model_validate({"version": 1, "description": None})

        assert update.model_dump(exclude_unset=True) == {"version": 1, "description": None}


def _check_values(model: type, constraint: str) -> set[str]:
    """The values listed by the `status IN (...)` CHECK constraint of a model."""
    check = next(
        c for c in model.__table__.constraints if str(getattr(c, "name", "")).endswith(constraint)
    )
    return set(re.findall(r"'([a-z_]+)'", str(check.sqltext)))


@pytest.mark.parametrize(
    ("model", "enum"), [(WorkshopORM, WorkshopStatus), (EnrollmentORM, EnrollmentStatus)]
)
def test_the_database_accepts_exactly_the_statuses_of_the_enum(model: type, enum: type):
    # The enum lives in schemas and the CHECK in the model; the layers contract keeps them
    # from importing each other, so this is what keeps them equal.
    assert _check_values(model, "status") == {member.value for member in enum}
