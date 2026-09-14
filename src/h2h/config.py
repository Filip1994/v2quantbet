"""Application configuration contracts."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True, repr=False)
class Config:
    app_env: str
    log_level: str
    database_url: str
    odds_api_key: str

    def __repr__(self) -> str:
        return (
            "Config("
            f"app_env={self.app_env!r}, "
            f"log_level={self.log_level!r}, "
            "database_url='[REDACTED]', "
            "odds_api_key='[REDACTED]'"
            ")"
        )


@dataclass(frozen=True, repr=False)
class ApplicationSettings:
    """Validated settings for the quote application boundary."""

    database_path: Path
    api_football_key: str = field(repr=False)

    def __repr__(self) -> str:
        return f"ApplicationSettings(database_path={str(self.database_path)!r}, api_football_key='[REDACTED]')"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required configuration: {name}")
    return value


def load_config() -> Config:
    """Load and validate the legacy application configuration."""
    app_env = _required("APP_ENV")
    log_level = _required("LOG_LEVEL").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError(f"Invalid LOG_LEVEL: {log_level}")

    return Config(
        app_env=app_env,
        log_level=log_level,
        database_url=_required("DATABASE_URL"),
        odds_api_key=_required("ODDS_API_KEY"),
    )


def load_settings(environ: Mapping[str, str] | None = None) -> ApplicationSettings:
    """Load quote application settings without exposing secrets in repr output."""
    values = os.environ if environ is None else environ
    api_key = values.get("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        raise ConfigError("Missing required configuration: API_FOOTBALL_KEY")

    database_path = values.get("QUANTBET_DATABASE_PATH", "data/quantbet.sqlite3").strip()
    if not database_path:
        raise ConfigError("QUANTBET_DATABASE_PATH must not be blank")

    return ApplicationSettings(
        database_path=Path(database_path),
        api_football_key=api_key,
    )
