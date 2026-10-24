"""Settings read from environment variables or the .env file (see .env.example)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Eagle Eye"
    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"
    database_url: str = "sqlite:///./eagle_eye.db"
    upload_dir: Path = Path("./uploads")
    max_upload_mb: int = 20
    detector_weights_path: str = ""
    detector_model_name: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
