"""The shared input types hold a value to what every layer below can take."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.schema import Timestamp

timestamp = TypeAdapter(Timestamp)


class TestTimestamp:
    def test_keeps_the_offset_it_was_sent_with(self):
        value = timestamp.validate_python("2030-05-04T10:00:00+02:00")

        assert value == datetime(2030, 5, 4, 8, tzinfo=UTC)
        assert value.utcoffset() == timedelta(hours=2)

    @pytest.mark.parametrize(
        "raw",
        [
            "2030-05-04T10:00:00",  # no offset: which 10:00?
            "0001-01-01T00:00:00+14:00",  # no UTC equivalent: the driver overflows on it
            "1899-12-31T23:59:59Z",
            "3000-01-01T00:00:00Z",
            "9999-12-31T23:59:59-12:00",
            "not a date",
        ],
        ids=["naive", "before-year-1", "too-early", "too-late", "past-year-9999", "garbage"],
    )
    def test_rejects(self, raw: str):
        with pytest.raises(ValidationError):
            timestamp.validate_python(raw)

    def test_the_bounds_are_compared_as_instants(self):
        # 1900-01-01T00:30+01:00 is 1899 in UTC.
        early = datetime(1900, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=1)))

        with pytest.raises(ValidationError):
            timestamp.validate_python(early)
