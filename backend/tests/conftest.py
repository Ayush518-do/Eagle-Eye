import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings, get_settings
from backend.app.main import app


@pytest.fixture
def client(tmp_path):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, upload_dir=tmp_path / "uploads", max_upload_mb=1
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
