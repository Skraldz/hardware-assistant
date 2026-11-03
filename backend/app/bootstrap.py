"""Create database tables if they do not exist yet, and add any columns a
model has gained since its table was first created.

Kept separate from app.main so importing the FastAPI app (e.g. in tests) never
touches the real database. Run explicitly before starting the API.

This project has no migration framework (Alembic) -- SPEC.md's own Phase 1
entry in docs/ai-log.md judged that proportionate for an exam project.
`Base.metadata.create_all()` only creates *missing tables*; it never alters
one that already exists. That silently broke the live deployment once
`SavedBuild.purpose` was added to a model whose table had already been
created on an earlier run: `create_all()` kept no-opping on the now-stale
`saved_builds` table, so every query touching `purpose` failed with
"Unknown column" at the database level (surfaced to the frontend as a 500).
`_sync_missing_columns()` is a deliberately minimal stand-in for a real
migration tool: after `create_all()`, it compares each mapped table's columns
against what the database actually has and issues `ALTER TABLE ... ADD
COLUMN` for anything missing. It never drops, renames, or alters an existing
column -- only ever adds one -- so it's safe to run on every container
start, the same way `seed()` already is. It only works for new columns that
are nullable (or have a server-side default), which matches every column
this project has actually added so far.
"""

from sqlalchemy import inspect, text

from app import models  # noqa: F401  registers models on Base.metadata
from app.db import Base, engine


def _sync_missing_columns() -> None:
    """Add columns that exist on the models but not yet in the database.

    A deliberately minimal stand-in for a migration tool: create_all() only
    ever creates missing tables, never alters existing ones, so a new column
    existed in the code but not in a running database -- which is exactly
    how saving a build started returning server errors. Only ever adds, never
    drops or alters, so it is safe on every container start.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # just created by create_all() above, already current
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                ddl_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl_type}"))


def main() -> None:
    """Create any missing tables, then add any missing columns."""
    Base.metadata.create_all(bind=engine)
    _sync_missing_columns()


if __name__ == "__main__":
    main()
