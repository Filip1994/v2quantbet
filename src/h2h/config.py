"""Application configuration contracts."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from h2h.domain.odds import Market, Selection
from h2h.domain.registration_policy import RegistrationPolicyConfig


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
    """Validated settings for the quote application boundary.

    ``database_path`` remains for legacy SQLite consumers. New PostgreSQL
    composition should use ``database_url`` when it is configured.
    """

    database_path: Path
    api_football_key: str = field(repr=False)
    database_url: str | None = field(default=None, repr=False)
    registration_policy: RegistrationPolicyConfig | None = None

    def __repr__(self) -> str:
        return (
            f"ApplicationSettings(database_path={str(self.database_path)!r}, "
            "database_url='[REDACTED]', api_football_key='[REDACTED]', "
            f"registration_policy={self.registration_policy!r})"
        )


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

    database_url = values.get("DATABASE_URL", "").strip() or None
    registration_names = _REGISTRATION_ENV_NAMES
    configured_policy = any(values.get(name, "").strip() for name in registration_names)
    registration_policy = load_registration_policy_config(values) if configured_policy else None

    return ApplicationSettings(
        database_path=Path(database_path),
        api_football_key=api_key,
        database_url=database_url,
        registration_policy=registration_policy,
    )


_REGISTRATION_ENV_NAMES = (
    "QUANTBET_ALLOWED_MARKET_SELECTIONS",
    "QUANTBET_ALLOWED_DEVIG_METHODS",
    "QUANTBET_ALLOWED_FIXTURE_STATUSES",
    "QUANTBET_MINIMUM_EDGE",
    "QUANTBET_MINIMUM_EXPECTED_VALUE",
    "QUANTBET_MINIMUM_ODDS",
    "QUANTBET_MAXIMUM_ODDS",
    "QUANTBET_MAXIMUM_QUOTE_AGE_SECONDS",
    "QUANTBET_MINIMUM_TIME_TO_KICKOFF_SECONDS",
    "QUANTBET_BANKROLL_ACCOUNT_ID",
    "QUANTBET_CURRENCY",
    "QUANTBET_INITIAL_BANKROLL_MINOR",
    "QUANTBET_FIXED_STAKE_MINOR",
    "QUANTBET_MAX_STAKE_PER_PICK_MINOR",
    "QUANTBET_MAX_OPEN_EXPOSURE_MINOR",
)


def _policy_required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required registration policy configuration: {name}")
    return value


def _policy_int(values: Mapping[str, str], name: str) -> int:
    raw = _policy_required(values, name)
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _policy_decimal(values: Mapping[str, str], name: str) -> Decimal:
    raw = _policy_required(values, name)
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ConfigError(f"{name} must be a decimal") from exc


def load_registration_policy_config(
    environ: Mapping[str, str] | None = None,
) -> RegistrationPolicyConfig:
    """Load a complete policy; partial or invalid decision configuration fails closed."""

    values = os.environ if environ is None else environ
    pairs: list[tuple[Market, Selection]] = []
    for raw_pair in _policy_required(values, "QUANTBET_ALLOWED_MARKET_SELECTIONS").split(","):
        parts = [part.strip() for part in raw_pair.split("/", 1)]
        if len(parts) != 2:
            raise ConfigError("QUANTBET_ALLOWED_MARKET_SELECTIONS must use MARKET/SELECTION")
        try:
            pairs.append((Market(parts[0]), Selection(parts[1])))
        except ValueError as exc:
            raise ConfigError(f"unsupported market/selection: {raw_pair!r}") from exc
    devig = tuple(
        part.strip()
        for part in _policy_required(values, "QUANTBET_ALLOWED_DEVIG_METHODS").split(",")
    )
    statuses = tuple(
        part.strip()
        for part in _policy_required(values, "QUANTBET_ALLOWED_FIXTURE_STATUSES").split(",")
    )
    try:
        return RegistrationPolicyConfig(
            allowed_market_selections=tuple(pairs),
            allowed_devig_methods=devig,
            allowed_fixture_statuses=statuses,
            minimum_edge=_policy_decimal(values, "QUANTBET_MINIMUM_EDGE"),
            minimum_expected_value=_policy_decimal(values, "QUANTBET_MINIMUM_EXPECTED_VALUE"),
            minimum_odds=_policy_decimal(values, "QUANTBET_MINIMUM_ODDS"),
            maximum_odds=_policy_decimal(values, "QUANTBET_MAXIMUM_ODDS"),
            maximum_quote_age_seconds=_policy_int(values, "QUANTBET_MAXIMUM_QUOTE_AGE_SECONDS"),
            minimum_time_to_kickoff_seconds=_policy_int(
                values, "QUANTBET_MINIMUM_TIME_TO_KICKOFF_SECONDS"
            ),
            bankroll_account_id=_policy_required(values, "QUANTBET_BANKROLL_ACCOUNT_ID"),
            currency=_policy_required(values, "QUANTBET_CURRENCY"),
            initial_bankroll_minor=_policy_int(values, "QUANTBET_INITIAL_BANKROLL_MINOR"),
            fixed_stake_minor=_policy_int(values, "QUANTBET_FIXED_STAKE_MINOR"),
            max_stake_per_pick_minor=_policy_int(values, "QUANTBET_MAX_STAKE_PER_PICK_MINOR"),
            max_open_exposure_minor=_policy_int(values, "QUANTBET_MAX_OPEN_EXPOSURE_MINOR"),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid registration policy configuration: {exc}") from exc
