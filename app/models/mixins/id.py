from sqlalchemy import BigInteger, Identity
from sqlalchemy.orm import Mapped, mapped_column


class IntPkMixin:
    """Provides a BIGINT GENERATED ALWAYS AS IDENTITY primary key."""

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
