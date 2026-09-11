"""Minimal application configuration contract."""

from __future__ import annotations

import os
from dataclasses import dataclass


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


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required configuration: {name}")
    return value


def load_config() -> Config:
    """Load and validate the minimal application configuration from environment variables."""
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
