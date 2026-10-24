"""Settings read from environment variables or the .env file (see .env.example).

Default paths are anchored to this file, not to the process's working directory. A relative
`UPLOAD_DIR` or SQLite `DATABASE_URL` from the environment is read relative to the repository
root (where `.env` lives and where the documented commands run), so it means the same thing
whichever directory the process starts in. Absolute values are used as given.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    app_name: str = "Eagle Eye"
    app_env: str = "development"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'eagle_eye.db').as_posix()}"
    upload_dir: Path = BACKEND_DIR / "uploads"
    max_upload_mb: int = 20
    detector_weights_path: str = ""
    detector_model_name: str = ""

    @field_validator("upload_dir")
    @classmethod
    def _anchor_upload_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else REPO_ROOT / value

    @field_validator("database_url")
    @classmethod
    def _anchor_sqlite_file(cls, value: str) -> str:
        url = make_url(value)
        if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
            return value
        if url.database.startswith("file:") or Path(url.database).is_absolute():
            return value
        anchored = (REPO_ROOT / url.database).resolve()
        return url.set(database=anchored.as_posix()).render_as_string(hide_password=False)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
