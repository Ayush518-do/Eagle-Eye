"""Migration 0003 (Contract A/B fields) and the migration hardening from Stage 1b."""
import os
import sqlite3
import subprocess
import sys
import threading

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.config import REPO_ROOT
from backend.app.db import make_engine
from backend.app.models import Cabinet, DesignRevision, ExpectedItem, Image, Inspection, Observation

from .conftest import alembic_config


def raw(url: str) -> sqlite3.Connection:
    """A plain sqlite3 connection: foreign keys off, no ORM guards."""
    return sqlite3.connect(url.removeprefix("sqlite:///"))


def columns(url: str, table: str) -> dict:
    engine = make_engine(url)
    cols = {c["name"]: c for c in inspect(engine).get_columns(table)}
    engine.dispose()
    return cols


def seed_image(s) -> str:
    s.add(Cabinet(id="CAB-001", name="x"))
    s.add(DesignRevision(id="D1", cabinet_id="CAB-001", label="REV-A", drawing_file_id="f",
                         drawing_sha256="0" * 64))
    s.flush()
    ins = Inspection(cabinet_id="CAB-001", design_revision_id="D1")
    s.add(ins)
    s.flush()
    img = Image(inspection_id=ins.id, file_id="f", sha256="0" * 64, width=10, height=10)
    s.add(img)
    s.commit()
    return img.id


def make_obs(image_id: str, observation_id: str) -> Observation:
    return Observation(image_id=image_id, observation_id=observation_id, source="manual",
                       kind="component", class_name="mcb", bbox=[1, 2, 3, 4])


# ---------- migration 0003 ----------
def test_0003_adds_contract_a_columns_as_nullable(migrated_db_url):
    cols = columns(migrated_db_url, "expected_items")
    for name in ("rating_source", "rating_page", "source_page"):
        assert cols[name]["nullable"] is True


def test_0003_makes_observation_id_required(migrated_db_url):
    assert columns(migrated_db_url, "observations")["observation_id"]["nullable"] is False


def test_0003_backfills_existing_observations_without_losing_rows(db_url):
    cfg = alembic_config(db_url)
    command.upgrade(cfg, "0002")
    c = raw(db_url)
    ts = "2026-01-01 00:00:00"
    c.execute("insert into cabinets values ('CAB-A','x',?)", (ts,))
    c.execute("insert into design_revisions values ('D1','CAB-A','REV-A','f','0',?)", (ts,))
    c.execute("insert into inspections (id,cabinet_id,design_revision_id,state,created_at) "
              "values ('I1','CAB-A','D1','queued',?)", (ts,))
    c.execute("insert into images values ('IMG-1','I1','f','0',10,10,'[]')")
    c.execute("insert into observations (id,image_id,source,kind,class_name,bbox) "
              "values ('OBS-OLD','IMG-1','manual','component','mcb','[1,2,3,4]')")
    c.execute("insert into expected_items (id,design_revision_id,tag,quantity,rating_needs_review) "
              "values ('ITEM-1','D1','CB11',1,0)")
    c.commit()
    c.close()
    command.upgrade(cfg, "head")
    c = raw(db_url)
    assert c.execute("select id, observation_id from observations").fetchall() == [("OBS-OLD", "OBS-OLD")]
    assert c.execute("select tag, rating_source from expected_items").fetchall() == [("CB11", None)]
    c.close()


def test_0003_downgrade_and_reupgrade(migrated_db_url):
    cfg = alembic_config(migrated_db_url)
    command.downgrade(cfg, "0002")
    assert "observation_id" not in columns(migrated_db_url, "observations")
    assert "rating_source" not in columns(migrated_db_url, "expected_items")
    command.upgrade(cfg, "head")
    assert "observation_id" in columns(migrated_db_url, "observations")


# ---------- Contract A / B persistence ----------
def test_expected_item_keeps_contract_a_rating_fields(session_factory):
    with session_factory() as s:
        s.add(Cabinet(id="CAB-001", name="x"))
        s.add(DesignRevision(id="D1", cabinet_id="CAB-001", label="REV-A", drawing_file_id="f",
                             drawing_sha256="0" * 64))
        s.flush()
        s.add(ExpectedItem(design_revision_id="D1", tag="CB11", rating_value="10 A",
                           rating_source="schematic", rating_page=5, source_page=3))
        s.add(ExpectedItem(design_revision_id="D1", tag="X1"))
        s.commit()
        a, b = s.query(ExpectedItem).order_by(ExpectedItem.tag).all()
        assert (a.rating_source, a.rating_page, a.source_page) == ("schematic", 5, 3)
        assert (b.rating_source, b.rating_page, b.source_page) == (None, None, None)


def test_observation_id_is_kept_separately_from_the_server_key(session_factory):
    with session_factory() as s:
        o = make_obs(seed_image(s), "OBS-001")
        s.add(o)
        s.commit()
        assert o.observation_id == "OBS-001" and o.id.startswith("OBS-") and o.id != "OBS-001"


def test_observation_id_may_repeat_across_images_but_not_within_one(session_factory):
    with session_factory() as s:
        first = seed_image(s)
        second = Image(inspection_id=s.get(Image, first).inspection_id, file_id="g",
                       sha256="1" * 64, width=10, height=10)
        s.add(second)
        s.commit()
        s.add_all([make_obs(first, "OBS-001"), make_obs(second.id, "OBS-001")])
        s.commit()
        s.add(make_obs(first, "OBS-001"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_database_blocks_duplicate_observation_ids_under_concurrent_inserts(session_factory, migrated_db_url):
    with session_factory() as s:
        image_id = seed_image(s)
    results: list[str] = []
    barrier = threading.Barrier(8)

    def insert() -> None:
        engine = make_engine(migrated_db_url)
        try:
            with sessionmaker(bind=engine)() as s2:
                s2.add(make_obs(image_id, "OBS-RACE"))
                barrier.wait()
                try:
                    s2.commit()
                    results.append("ok")
                except IntegrityError:
                    results.append("duplicate")
                except Exception as e:  # SQLite may report a locked database instead
                    results.append(type(e).__name__)
        finally:
            engine.dispose()

    threads = [threading.Thread(target=insert) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    c = raw(migrated_db_url)
    stored = c.execute("select count(*) from observations where observation_id='OBS-RACE'").fetchone()[0]
    c.close()
    assert results.count("ok") == 1 and stored == 1, results


# ---------- migration hardening ----------
def test_application_connections_keep_foreign_keys_on(migrated_db_url):
    engine = make_engine(migrated_db_url)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    engine.dispose()
    off = make_engine(migrated_db_url, foreign_keys=False)
    with off.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
    off.dispose()


def test_migration_fails_loudly_when_it_would_leave_a_foreign_key_violation(db_url):
    cfg = alembic_config(db_url)
    command.upgrade(cfg, "0002")
    c = raw(db_url)  # plain sqlite3, so an orphan row can be written
    c.execute("insert into observations (id,image_id,source,kind,class_name,bbox) "
              "values ('OBS-1','IMG-GONE','manual','component','mcb','[]')")
    c.commit()
    c.close()
    with pytest.raises(RuntimeError, match="Foreign key check failed"):
        command.upgrade(cfg, "head")


def test_rebuilding_a_parent_table_with_data_passes_with_enforcement_off(migrated_db_url):
    """The case that failed while migrations ran with foreign keys enforced."""
    engine = make_engine(migrated_db_url, foreign_keys=False)
    with engine.connect() as conn:
        conn.exec_driver_sql("insert into cabinets values ('CAB-A','x','2026-01-01 00:00:00')")
        conn.exec_driver_sql(
            "insert into design_revisions (id,cabinet_id,label,drawing_file_id,drawing_sha256,created_at) "
            "values ('D1','CAB-A','REV-A','f','0','2026-01-01 00:00:00')")
        conn.exec_driver_sql(
            "insert into inspections (id,cabinet_id,design_revision_id,state,created_at) "
            "values ('I1','CAB-A','D1','queued','2026-01-01 00:00:00')")
        conn.commit()
        ops = Operations(MigrationContext.configure(conn))
        with ops.batch_alter_table("design_revisions", recreate="always") as b:
            b.add_column(sa.Column("probe", sa.String(5), nullable=True))
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        assert conn.exec_driver_sql("select count(*) from design_revisions").scalar() == 1
    engine.dispose()


@pytest.mark.parametrize("from_backend", [False, True], ids=["from-repo-root", "from-backend"])
def test_alembic_cli_works_from_both_directories(tmp_path, from_backend):
    url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    cwd = REPO_ROOT / "backend" if from_backend else REPO_ROOT
    ini = "alembic.ini" if from_backend else "backend/alembic.ini"
    env = {**os.environ, "DATABASE_URL": url}
    env.pop("PYTHONPATH", None)
    last = None
    for args in (["upgrade", "head"], ["current"]):
        last = subprocess.run([sys.executable, "-m", "alembic", "-c", ini, *args], cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=120)
        assert last.returncode == 0, last.stderr
    assert "0006" in last.stdout + last.stderr
