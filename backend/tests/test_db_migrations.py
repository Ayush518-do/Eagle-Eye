import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from backend.app.db import make_engine
from backend.app.models import Base, Cabinet, DesignRevision, Inspection

from .conftest import alembic_config

TABLES = {
    "cabinets", "design_revisions", "expected_items", "inspections",
    "images", "observations", "findings", "review_events",
}


def test_upgrade_creates_the_eight_documented_tables(migrated_db_url):
    engine = make_engine(migrated_db_url)
    assert set(inspect(engine).get_table_names()) - {"alembic_version"} == TABLES
    engine.dispose()


def test_migration_matches_models(migrated_db_url):
    """Fails if someone changes models.py without adding a migration."""
    engine = make_engine(migrated_db_url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == []


def test_downgrade_removes_everything(migrated_db_url):
    command.downgrade(alembic_config(migrated_db_url), "base")
    engine = make_engine(migrated_db_url)
    assert set(inspect(engine).get_table_names()) - {"alembic_version"} == set()
    engine.dispose()


def test_foreign_keys_are_enforced(session_factory):
    with session_factory() as s:
        s.add(DesignRevision(cabinet_id="CAB-NOPE", label="REV-A", drawing_file_id="f", drawing_sha256="0" * 64))
        with pytest.raises(IntegrityError):
            s.commit()


def test_inspection_state_is_restricted(session_factory):
    with session_factory() as s:
        s.add(Cabinet(id="CAB-001", name="Line 3"))
        s.add(DesignRevision(id="D1", cabinet_id="CAB-001", label="REV-A", drawing_file_id="f",
                             drawing_sha256="0" * 64))
        s.commit()
        s.add(Inspection(cabinet_id="CAB-001", design_revision_id="D1", state="approved"))
        with pytest.raises(IntegrityError):
            s.commit()
