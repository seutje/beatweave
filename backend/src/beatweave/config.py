from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    return Path.home() / ".beatweave"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BEATWEAVE_", env_file=".env", extra="ignore")

    app_name: str = "Beatweave"
    host: str = "127.0.0.1"
    port: int = 8420
    log_level: str = "INFO"
    data_dir: Path = Field(default_factory=default_data_dir)
    database_path: Path | None = None

    @property
    def resolved_database_path(self) -> Path:
        return self.database_path or self.data_dir / "beatweave.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
