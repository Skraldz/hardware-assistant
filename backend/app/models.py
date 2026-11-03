"""SQLAlchemy ORM models: the two tables this project stores.

One table for inventory components and one for builds the user saved. See
each class for why the schema is shaped the way it is.
"""

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
    """One piece of hardware in the user's inventory.

    Category-independent fields are real columns; the category-specific
    specifications live in the `specs` JSON column, because the eight
    categories have almost nothing in common. Type safety is restored in the
    application layer by schemas/components.py's discriminated union.

    `release_year` is deliberately a column rather than part of `specs`: it
    is metadata about the product rather than a technical capability, and
    keeping it top-level is what makes era-based requests ("hardware from
    2010 or earlier") expressible at all.

    Attributes:
        category: Which of the eight kinds of hardware this is.
        name: Product name as the user or the extraction recorded it.
        manufacturer: Brand, optional.
        release_year: When the product launched, optional.
        quantity: How many are owned; 0 keeps the row but excludes it from
            recommendations.
        condition: New, used, or faulty.
        specs: Category-specific specifications as JSON.
        specs_source: Whether the specs were typed, extracted, or seeded.
        specs_verified: Whether the user confirmed them.
        source_url: The page the specs were extracted from, if any.
        notes: Free text.
    """

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
    # The page an auto-looked-up component had its specs extracted from, so a
    # user can check the claim later. Recorded by /extract (the URL the
    # backend actually fetched), not typed by hand, and null for manual and
    # seeded components. Provenance only -- no rule or pipeline step reads it.
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SavedBuild(Base):
    """A build the user chose to keep.

    Stores the components as JSON rather than as foreign keys, so a saved
    build survives the component rows being edited or deleted -- it is a
    record of what was recommended at the time, not a live view.

    Attributes:
        name: What the user called it.
        purpose: The original free-text ask that produced it.
        components: The chosen components as JSON.
        completed: Whether the machine has actually been assembled, which is
            what decrements the components' quantity.
    """

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
