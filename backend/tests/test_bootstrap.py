"""Regression test for the real bug this fixed on the live deployment:
Base.metadata.create_all() only creates missing tables, so a table created
before a column existed on its model (e.g. SavedBuild.purpose, added after
the table already existed) stays stale forever and every query touching that
column fails at the database level. _sync_missing_columns() must repair that
without touching any existing data.
"""

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

from app.bootstrap import _sync_missing_columns
from app.db import Base


def test_sync_missing_columns_adds_a_column_to_a_stale_table(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    # Simulate a table created by an older version of the model, before a
    # column (here "purpose") was added to it.
    stale_metadata = MetaData()
    Table(
        "saved_builds",
        stale_metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(200)),
    )
    stale_metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO saved_builds (id, name) VALUES (1, 'Existing build')"))

    monkeypatch.setattr("app.bootstrap.engine", engine)
    _sync_missing_columns()

    columns = {col["name"] for col in inspect(engine).get_columns("saved_builds")}
    assert {c.name for c in Base.metadata.tables["saved_builds"].columns} <= columns

    # Existing data survives untouched; the new column is nullable.
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, name, purpose FROM saved_builds WHERE id = 1")).fetchone()
    assert row == (1, "Existing build", None)


def test_sync_missing_columns_is_a_noop_for_an_up_to_date_table(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr("app.bootstrap.engine", engine)
    Base.metadata.create_all(bind=engine)

    _sync_missing_columns()  # must not raise on tables that are already current
