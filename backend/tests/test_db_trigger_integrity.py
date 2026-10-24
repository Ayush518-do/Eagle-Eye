"""Append-only triggers must survive every migration up to the latest revision."""
import sqlite3

import pytest
from alembic import command
from sqlalchemy import text

from backend.app.db import make_engine

from .conftest import alembic_config
from .test_db_triggers import TRIGGERS, counts, trigger_names


def test_latest_revision_has_every_required_trigger_with_the_right_definition(migrated_db_url):
    """Fails if a later migration rebuilds findings/review_events and forgets the triggers."""
    engine = make_engine(migrated_db_url)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger'")).all()
    engine.dispose()
    assert {r[0] for r in rows} == TRIGGERS
    for _name, table, sql in rows:
        assert table in {"findings", "review_events"}
        assert "BEFORE" in sql.upper() and "RAISE(ABORT" in sql


def test_upgrading_a_database_that_holds_history_keeps_triggers_and_data(db_url):
    cfg = alembic_config(db_url)
    command.upgrade(cfg, "0002")
    c = sqlite3.connect(db_url.removeprefix("sqlite:///"))  # raw SQL: the models describe head, not 0002
    ts = "2026-01-01 00:00:00"
    c.execute("insert into cabinets values ('CAB-001','x',?)", (ts,))
    c.execute("insert into design_revisions (id,cabinet_id,label,drawing_file_id,drawing_sha256,created_at) "
              "values ('D1','CAB-001','REV-A','f','0',?)", (ts,))
    c.execute("insert into inspections (id,cabinet_id,design_revision_id,state,created_at) "
              "values ('I1','CAB-001','D1','queued',?)", (ts,))
    c.execute("insert into findings (id,inspection_id,type,status,evidence) "
              "values ('F1','I1','rating_mismatch','needs_review','[]')")
    c.execute("insert into review_events (finding_id,decision,reviewer,note,created_at) "
              "values ('F1','confirmed_by_reviewer','A','n',?)", (ts,))
    c.commit()
    c.close()
    command.upgrade(cfg, "head")
    assert trigger_names(db_url) == TRIGGERS
    assert counts(db_url) == (1, 1, "needs_review", "n")
    conn = sqlite3.connect(db_url.removeprefix("sqlite:///"))
    with pytest.raises(sqlite3.IntegrityError, match="immutable|append-only"):
        conn.execute("UPDATE findings SET status='verified'")
    conn.close()
