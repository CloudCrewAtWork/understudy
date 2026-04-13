"""Settings loader. All env vars prefixed UNDERSTUDY_ except the Anthropic key."""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="UNDERSTUDY_",
        extra="ignore",
        case_sensitive=False,
    )

    anthropic_api_key: SecretStr = Field(default=SecretStr(""), alias="ANTHROPIC_API_KEY")

    data_dir: Path = Field(default=Path("~/.understudy"))
    db_path: Path = Field(default=Path("~/.understudy/understudy.db"))
    retention_days: int = Field(default=7, ge=1, le=365)
    model: str = Field(default="claude-sonnet-4-5")
    induction_model: str = Field(default="claude-sonnet-4-5")
    max_steps: int = Field(default=50, ge=1, le=500)
    log_level: str = Field(default="INFO")
    db_key: SecretStr | None = Field(default=None)
    redaction_strict: bool = Field(default=True)
    screenshots: bool = Field(default=False)

    def expanded_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()

    def expanded_db_path(self) -> Path:
        return self.db_path.expanduser().resolve()

    def trajectories_dir(self) -> Path:
        return self.expanded_data_dir() / "trajectories"

    def replays_dir(self) -> Path:
        return self.expanded_data_dir() / "replays"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        os.umask(0o077)
        _settings = Settings()
        _ensure_dirs(_settings)
        _configure_logging(_settings)
    return _settings


def _ensure_dirs(s: Settings) -> None:
    for d in (s.expanded_data_dir(), s.trajectories_dir(), s.replays_dir()):
        d.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            d.chmod(0o700)


def _configure_logging(s: Settings) -> None:
    from rich.logging import RichHandler

    level = getattr(logging, s.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )
