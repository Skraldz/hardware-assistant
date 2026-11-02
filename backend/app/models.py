from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, CheckConstraint, DateTime, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import Category, Condition, SpecsSource


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    """Store Python Enum .value (e.g. "cpu") instead of SQLAlchemy's .name default ("CPU")."""
    return [member.value for member in enum_cls]


class Component(Base):
    __tablename__ = "components"
    __table_args__ = (CheckConstraint("quantity >= 0", name="ck_components_quantity_nonnegative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[Category] = mapped_column(
        SAEnum(Category, native_enum=False, length=20, values_callable=_enum_values),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    release_year: Mapped[int | None] = mapped_column(nullable=True)
    quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    condition: Mapped[Condition] = mapped_column(
        SAEnum(Condition, native_enum=False, length=20, values_callable=_enum_values),
        nullable=False,
        default=Condition.NEW,
    )
    specs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    specs_source: Mapped[SpecsSource] = mapped_column(
        SAEnum(SpecsSource, native_enum=False, length=20, values_callable=_enum_values),
        nullable=False,
        default=SpecsSource.MANUAL,
    )
    specs_verified: Mapped[bool] = mapped_column(nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SavedBuild(Base):
    __tablename__ = "saved_builds"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # A snapshot of the build's components (id/category/name) at save time,
    # so the saved build stays fully displayable even if a component is
    # later edited or deleted -- completing the build (routers/builds.py)
    # still acts on the live components by id, for whichever still exist.
    components: Mapped[list] = mapped_column(JSON, nullable=False)
    # Why the *user* wanted this build (e.g. "play Baldur's Gate 3 at max
    # resolution and 60 FPS") -- the original ask, distinct from `reason`
    # below, which is the ranking LLM's justification for picking this
    # specific build over the other candidates.
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
