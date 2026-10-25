from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.app.config import Settings, get_settings
from backend.app.db import make_engine
from backend.app.main import app

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture(autouse=True)
def _restore_pillow_max_image_pixels():
    default = 1024 * 1024 * 1024 // 4 // 3
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = default
    yield
    Image.MAX_IMAGE_PIXELS = default


@pytest.fixture
def api(tmp_path):
    """TestClient on a fresh migrated temporary database and a temporary upload folder."""
    url = f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    command.upgrade(alembic_config(url), "head")
    settings = Settings(_env_file=None, database_url=url, upload_dir=tmp_path / "uploads", max_upload_mb=1)
    app.dependency_overrides[get_settings] = lambda: settings
    test_client = TestClient(app)
    test_client.settings = settings
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, upload_dir=tmp_path / "uploads", max_upload_mb=1
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- database fixtures ----------
def alembic_config(db_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    return cfg


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def migrated_db_url(db_url):
    """A fresh temporary database built by the real Alembic migrations."""
    command.upgrade(alembic_config(db_url), "head")
    return db_url


@pytest.fixture
def session_factory(migrated_db_url):
    engine = make_engine(migrated_db_url)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()
