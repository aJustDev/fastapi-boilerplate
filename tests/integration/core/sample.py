"""A model of the tests' own, for what is about the infrastructure and not about a context.

The repository and its pagination are tested against it, so replacing the example context
leaves those tests alone. Its table lives in a schema of its own, created by the fixture
in conftest.py: the tests that compare the models with the migrations look at `public`.
"""

from sqlalchemy import BigInteger, Integer, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import NAMING_CONVENTION, AuditMixin, Base, IntPkMixin
from app.core.repo import BaseRepo, FieldMapping

SCHEMA = "test_support"


class SampleBase(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)
    type_annotation_map = Base.type_annotation_map


class SampleORM(SampleBase, IntPkMixin, AuditMixin):
    __tablename__ = "samples"

    name: Mapped[str]
    category: Mapped[str] = mapped_column(default="general")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    owner_id: Mapped[int] = mapped_column(BigInteger)


class SampleRepo(BaseRepo[SampleORM]):
    model = SampleORM
    map_field: dict[str, FieldMapping] = {
        "name": {"column": SampleORM.name, "op": "ilike"},
        "category": {"column": SampleORM.category, "op": "eq"},
        "priority": {"column": SampleORM.priority, "op": "eq"},
        "min_priority": {"column": SampleORM.priority, "op": "gte"},
        "max_priority": {"column": SampleORM.priority, "op": "lte"},
        "is_active": {"column": SampleORM.is_active, "op": "eq"},
        "owner_id": {"column": SampleORM.owner_id, "op": "eq"},
    }
