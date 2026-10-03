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
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    mcp_request_timeout_seconds: float = Field(default=900, ge=1, le=7200)
    beat_this_model: str = "final0"
    beat_this_device: str = "auto"
    beat_this_model_directory: Path | None = None
    data_dir: Path = Field(default_factory=default_data_dir)
    database_path: Path | None = None
    project_backup_interval_seconds: float = Field(default=300, ge=0)

    @property
    def resolved_database_path(self) -> Path:
        return self.database_path or self.data_dir / "beatweave.db"

    @property
    def resolved_beat_this_model_directory(self) -> Path:
        return self.beat_this_model_directory or self.data_dir / "models" / "beat-this"

    @property
    def resolved_log_path(self) -> Path:
        directory = self.database_path.parent if self.database_path is not None else self.data_dir
        return directory / "beatweave.log.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
