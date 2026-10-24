import sqlite3

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.db import make_engine
from backend.app.models import ReviewEvent

from .conftest import alembic_config
from .test_db_models import seed_finding

TRIGGERS = {
    "findings_no_update", "findings_no_delete",
    "review_events_no_update", "review_events_no_delete",
}


def trigger_names(db_url: str) -> set[str]:
    engine = make_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'")).all()
    engine.dispose()
    return {r[0] for r in rows}


def seed(session_factory):
    with session_factory() as s:
        f = seed_finding(s)
        s.add(ReviewEvent(finding_id=f.id, decision="confirmed_by_reviewer", reviewer="A", note="n"))
        s.commit()
        return f.id


def raw(db_url: str) -> sqlite3.Connection:
    """A plain sqlite3 connection: no SQLAlchemy, no ORM guards."""
    return sqlite3.connect(db_url.removeprefix("sqlite:///"))


def counts(db_url: str) -> tuple:
    with raw(db_url) as c:
        return (c.execute("select count(*) from findings").fetchone()[0],
                c.execute("select count(*) from review_events").fetchone()[0],
                c.execute("select status from findings").fetchone()[0],
                c.execute("select note from review_events").fetchone()[0])


@pytest.mark.parametrize("sql", [
    "UPDATE findings SET status='verified'",
    "UPDATE findings SET reason='x' WHERE 1=1",
    "DELETE FROM findings",
    "UPDATE review_events SET note='rewritten'",
    "UPDATE review_events SET decision='rejected_by_reviewer'",
    "DELETE FROM review_events",
])
def test_raw_sql_cannot_change_history(session_factory, migrated_db_url, sql):
    seed(session_factory)
    conn = raw(migrated_db_url)
    with pytest.raises(sqlite3.IntegrityError, match="immutable|append-only"):
        conn.execute(sql)
    conn.close()
    assert counts(migrated_db_url) == (1, 1, "needs_review", "n")


def test_core_statements_cannot_change_history(session_factory, migrated_db_url):
    seed(session_factory)
    engine = make_engine(migrated_db_url)
    for sql in ("UPDATE findings SET status='verified'", "DELETE FROM review_events"):
        with pytest.raises(DBAPIError, match="immutable|append-only"):
            with engine.begin() as conn:
                conn.execute(text(sql))
    engine.dispose()
    assert counts(migrated_db_url) == (1, 1, "needs_review", "n")


def test_inserts_and_ordinary_updates_still_work(session_factory, migrated_db_url):
    fid = seed(session_factory)
    conn = raw(migrated_db_url)
    conn.execute("INSERT INTO review_events (finding_id, decision, reviewer, note, created_at) "
                 "VALUES (?, 'rejected_by_reviewer', 'B', '', '2026-01-01 00:00:00')", (fid,))
    conn.execute("UPDATE inspections SET state='running'")
    conn.commit()
    assert conn.execute("select count(*) from review_events").fetchone()[0] == 2
    assert conn.execute("select state from inspections").fetchone()[0] == "running"
    conn.close()


def test_upgrade_creates_the_four_triggers(migrated_db_url):
    assert trigger_names(migrated_db_url) == TRIGGERS


def test_downgrade_one_step_removes_triggers_and_keeps_data(session_factory, migrated_db_url):
    seed(session_factory)
    cfg = alembic_config(migrated_db_url)
    command.downgrade(cfg, "0001")
    assert trigger_names(migrated_db_url) == set()
    assert counts(migrated_db_url) == (1, 1, "needs_review", "n")
    command.upgrade(cfg, "head")
    assert trigger_names(migrated_db_url) == TRIGGERS
    assert counts(migrated_db_url) == (1, 1, "needs_review", "n")


def test_downgrade_to_base_works_with_data_and_triggers_present(session_factory, migrated_db_url):
    seed(session_factory)
    command.downgrade(alembic_config(migrated_db_url), "base")
    assert trigger_names(migrated_db_url) == set()
    engine = make_engine(migrated_db_url)
    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    engine.dispose()
    assert tables - {"alembic_version"} == set()


def test_upgrade_from_nothing_in_two_steps(db_url):
    cfg = alembic_config(db_url)
    command.upgrade(cfg, "0001")
    assert trigger_names(db_url) == set()
    command.upgrade(cfg, "0002")
    assert trigger_names(db_url) == TRIGGERS
