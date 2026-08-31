"""Reseeding has to survive a schema change, not just a stale row.

D24 migrates by reseed. But `--force` wiped ROWS and left the tables as they
were, so a database written before a column existed stayed broken however many
times you reseeded -- the failure was `table ... has no column named
rate_provenance`, thrown from the INSERT, after the wipe had already run.

That is the state a teammate's clone lands in after pulling a schema change,
and the state the packaged app lands in with no shell to fix it from.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, inspect

from dynamic_pricing.db import rebuild_schema
from dynamic_pricing.models import Base


def test_rebuilding_restores_a_column_the_models_have_since_added(tmp_path: Path):
    db = tmp_path / "stale.db"
    engine = create_engine(f"sqlite:///{db}", future=True)
    Base.metadata.create_all(bind=engine)
    engine.dispose()

    # Age the database: drop a column the models still declare.
    conn = sqlite3.connect(db)
    # SQLite refuses to drop an indexed column, so the index goes first. The
    # end state is what matters: a table the models have outgrown.
    conn.execute("DROP INDEX IF EXISTS ix_operator_decisions_group_id")
    conn.execute("ALTER TABLE operator_decisions DROP COLUMN group_id")
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{db}", future=True)
    assert "group_id" not in {c["name"] for c in inspect(engine).get_columns("operator_decisions")}

    rebuild_schema(engine)

    assert "group_id" in {c["name"] for c in inspect(engine).get_columns("operator_decisions")}


def test_rebuilding_restores_a_table_that_did_not_exist_yet(tmp_path: Path):
    db = tmp_path / "stale.db"
    engine = create_engine(f"sqlite:///{db}", future=True)
    Base.metadata.create_all(bind=engine)
    engine.dispose()

    conn = sqlite3.connect(db)
    conn.execute("DROP TABLE seasons")
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{db}", future=True)
    rebuild_schema(engine)

    assert "seasons" in inspect(engine).get_table_names()


def test_rebuilding_an_empty_database_just_creates_the_schema(tmp_path: Path):
    """A teammate's first run has no file at all. That is not an error."""
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)

    rebuild_schema(engine)

    assert "seasons" in inspect(engine).get_table_names()
