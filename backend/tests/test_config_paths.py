from pathlib import Path

from sqlalchemy.engine import make_url

from backend.app.config import BACKEND_DIR, REPO_ROOT, Settings


def settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_defaults_do_not_depend_on_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = settings()
    assert s.upload_dir == BACKEND_DIR / "uploads"
    assert Path(make_url(s.database_url).database) == BACKEND_DIR / "eagle_eye.db"


def test_default_database_url_survives_spaces_and_parentheses():
    # The checkout path of this project can contain both; the URL must round-trip.
    assert Path(make_url(settings().database_url).database).parent == BACKEND_DIR


def test_relative_environment_values_are_anchored_to_the_repo_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = settings(upload_dir="./uploads", database_url="sqlite:///./eagle_eye.db")
    assert s.upload_dir == REPO_ROOT / "uploads"
    assert Path(make_url(s.database_url).database) == (REPO_ROOT / "eagle_eye.db").resolve()


def test_absolute_overrides_are_kept(tmp_path):
    url = f"sqlite:///{(tmp_path / 'x.db').as_posix()}"
    s = settings(upload_dir=tmp_path / "up", database_url=url)
    assert s.upload_dir == tmp_path / "up"
    assert s.database_url == url


def test_memory_and_non_sqlite_urls_are_left_alone():
    assert settings(database_url="sqlite://").database_url == "sqlite://"
    assert settings(database_url="sqlite:///:memory:").database_url == "sqlite:///:memory:"
    pg = "postgresql://u:p@host/db"
    assert settings(database_url=pg).database_url == pg


def test_default_paths_are_covered_by_gitignore():
    ignore = (REPO_ROOT / ".gitignore").read_text()
    assert "backend/uploads/" in ignore and "*.db" in ignore
