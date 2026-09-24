"""Application configuration contracts."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import timedelta

from h2h.domain.odds import Market, Selection
from h2h.domain.pick_monitoring import OddsLifecyclePolicy
from h2h.domain.registration_policy import RegistrationPolicyConfig
from h2h.domain.settlement import ResultSettlementPolicy
from h2h.domain.bookmaker_policy import API_FOOTBALL_BOOKMAKERS
from h2h.domain.model_coverage import ProductionTrainingPolicy
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy


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
    odds_lifecycle_policy: OddsLifecyclePolicy | None = None
    result_settlement_policy: ResultSettlementPolicy = field(default_factory=ResultSettlementPolicy)
    bulletin_timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Belgrade"))

    def __repr__(self) -> str:
        return (
            f"ApplicationSettings(database_path={str(self.database_path)!r}, "
            "database_url='[REDACTED]', api_football_key='[REDACTED]', "
            f"registration_policy={self.registration_policy!r}, "
            f"odds_lifecycle_policy={self.odds_lifecycle_policy!r}, "
            f"result_settlement_policy={self.result_settlement_policy!r}, "
            f"bulletin_timezone={self.bulletin_timezone.key!r})"
        )


@dataclass(frozen=True, repr=False)
class ProductionSettings:
    app_env: str
    log_level: str
    application: ApplicationSettings
    bookmaker_id: int
    bankroll_bootstrap_mode: str
    discovery_interval_seconds: float
    discovery_lookahead_hours: float
    opportunity_interval_seconds: float
    opportunity_max_items: int
    opportunity_max_wall_seconds: float
    api_football_published_max_age_seconds: int
    live_close_poll_seconds: float
    live_close_window_seconds: int
    live_close_max_age_seconds: int
    stale_quote_retry_policy: StaleQuoteRetryPolicy
    model_training_interval_seconds: float
    model_training_max_scopes: int
    model_training_max_provider_requests: int
    model_training_max_wall_seconds: float
    model_training_daily_limit: int
    model_training_operational_reserve: int
    model_training_policy: ProductionTrainingPolicy
    scheduler_tick_seconds: float
    shutdown_grace_seconds: float
    api_daily_limit: int
    api_reserve: int
    api_timeout_seconds: float
    database_startup_attempts: int
    database_startup_backoff_seconds: float
    port: int

    def __repr__(self) -> str:
        return (
            f"ProductionSettings(app_env={self.app_env!r}, log_level={self.log_level!r}, "
            "application=[REDACTED], "
            f"bookmaker_id={self.bookmaker_id!r}, "
            f"bankroll_bootstrap_mode={self.bankroll_bootstrap_mode!r})"
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
    lifecycle_names = _LIFECYCLE_ENV_NAMES
    configured_lifecycle = any(values.get(name, "").strip() for name in lifecycle_names)
    odds_lifecycle_policy = (
        load_odds_lifecycle_policy(values) if configured_lifecycle else None
    )
    result_settlement_policy = load_result_settlement_policy(values)
    timezone_name = values.get("QUANTBET_BULLETIN_TIMEZONE", "Europe/Belgrade").strip()
    if not timezone_name:
        raise ConfigError("QUANTBET_BULLETIN_TIMEZONE must not be blank")
    try:
        bulletin_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError("QUANTBET_BULLETIN_TIMEZONE must be a valid IANA timezone") from exc

    return ApplicationSettings(
        database_path=Path(database_path),
        api_football_key=api_key,
        database_url=database_url,
        registration_policy=registration_policy,
        odds_lifecycle_policy=odds_lifecycle_policy,
        result_settlement_policy=result_settlement_policy,
        bulletin_timezone=bulletin_timezone,
    )


def _positive_number(values: Mapping[str, str], name: str, default: str) -> float:
    raw = values.get(name, default).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive number")
    return value


def _positive_integer(values: Mapping[str, str], name: str, default: str) -> int:
    raw = values.get(name, default).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return value


def _nonnegative_integer(values: Mapping[str, str], name: str, default: str) -> int:
    raw = values.get(name, default).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a non-negative integer") from exc
    if value < 0:
        raise ConfigError(f"{name} must be a non-negative integer")
    return value


def load_production_settings(environ: Mapping[str, str] | None = None) -> ProductionSettings:
    """Load the complete single-service production contract; partial input fails closed."""
    values = os.environ if environ is None else environ
    app_env = values.get("APP_ENV", "").strip().lower()
    if app_env != "production":
        raise ConfigError("APP_ENV must be production for the production runtime")
    log_level = values.get("LOG_LEVEL", "").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    application = load_settings(values)
    if not application.database_url:
        raise ConfigError("Missing required configuration: DATABASE_URL")
    if application.registration_policy is None:
        raise ConfigError("complete registration policy configuration is required")
    if application.odds_lifecycle_policy is None:
        raise ConfigError("complete odds lifecycle configuration is required")

    bookmaker_id = _positive_integer(values, "QUANTBET_BOOKMAKER_ID", "0")
    if bookmaker_id not in API_FOOTBALL_BOOKMAKERS:
        raise ConfigError("QUANTBET_BOOKMAKER_ID is not a supported bookmaker")

    mode = values.get("QUANTBET_BANKROLL_BOOTSTRAP_MODE", "").strip().lower()
    if mode not in {"create", "verify"}:
        raise ConfigError("QUANTBET_BANKROLL_BOOTSTRAP_MODE must be create or verify")
    api_limit = _positive_integer(values, "QUANTBET_API_DAILY_LIMIT", "7500")
    api_reserve = int(values.get("QUANTBET_API_RESERVE", "0").strip())
    if api_reserve < 0 or api_reserve >= api_limit:
        raise ConfigError("QUANTBET_API_RESERVE must be non-negative and below the daily limit")
    effective_limit = api_limit - api_reserve
    training_daily_limit = _positive_integer(
        values, "QUANTBET_MODEL_TRAINING_DAILY_REQUEST_LIMIT", str(effective_limit)
    )
    training_operational_reserve = _nonnegative_integer(
        values, "QUANTBET_MODEL_TRAINING_OPERATIONAL_RESERVE", "0"
    )
    if training_daily_limit > effective_limit:
        raise ConfigError(
            "QUANTBET_MODEL_TRAINING_DAILY_REQUEST_LIMIT must not exceed effective API capacity"
        )
    if training_operational_reserve >= effective_limit:
        raise ConfigError(
            "QUANTBET_MODEL_TRAINING_OPERATIONAL_RESERVE must be below effective API capacity"
        )
    try:
        training_policy = ProductionTrainingPolicy(
            history_window_days=_positive_integer(
                values, "QUANTBET_MODEL_HISTORY_WINDOW_DAYS", "730"
            ),
            min_matches=_positive_integer(values, "QUANTBET_MODEL_MIN_MATCHES", "80"),
            xi=float(values.get("QUANTBET_MODEL_XI", "0.0018").strip()),
            ridge=float(values.get("QUANTBET_MODEL_RIDGE", "0.01").strip()),
            freshness_days=_positive_integer(
                values, "QUANTBET_MODEL_FRESHNESS_DAYS", "14"
            ),
            previous_seasons=_nonnegative_integer(
                values, "QUANTBET_MODEL_PREVIOUS_SEASONS", "1"
            ),
            min_team_matches=_positive_integer(
                values, "QUANTBET_MODEL_MIN_TEAM_MATCHES", "3"
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid model training policy: {exc}") from exc
    port = _positive_integer(values, "PORT", "8080")
    if port > 65535:
        raise ConfigError("PORT must be at most 65535")
    provider_published_max_age = _positive_integer(
        values, "QUANTBET_API_FOOTBALL_PUBLISHED_MAX_AGE_SECONDS", "14400"
    )
    if (
        provider_published_max_age
        < application.registration_policy.maximum_quote_age_seconds
    ):
        raise ConfigError(
            "QUANTBET_API_FOOTBALL_PUBLISHED_MAX_AGE_SECONDS must be at least "
            "QUANTBET_MAXIMUM_QUOTE_AGE_SECONDS"
        )
    return ProductionSettings(
        app_env=app_env,
        log_level=log_level,
        application=application,
        bookmaker_id=bookmaker_id,
        bankroll_bootstrap_mode=mode,
        discovery_interval_seconds=_positive_number(
            values, "QUANTBET_DISCOVERY_INTERVAL_SECONDS", "900"
        ),
        discovery_lookahead_hours=_positive_number(
            values, "QUANTBET_DISCOVERY_LOOKAHEAD_HOURS", "72"
        ),
        opportunity_interval_seconds=_positive_number(
            values, "QUANTBET_OPPORTUNITY_INTERVAL_SECONDS", "60"
        ),
        opportunity_max_items=_positive_integer(
            values, "QUANTBET_OPPORTUNITY_MAX_ITEMS", "10"
        ),
        opportunity_max_wall_seconds=_positive_number(
            values, "QUANTBET_OPPORTUNITY_MAX_WALL_SECONDS", "30"
        ),
        api_football_published_max_age_seconds=provider_published_max_age,
        live_close_poll_seconds=_positive_number(
            values, "QUANTBET_LIVE_CLOSE_POLL_SECONDS", "60"
        ),
        live_close_window_seconds=_positive_integer(
            values, "QUANTBET_LIVE_CLOSE_WINDOW_SECONDS", "900"
        ),
        live_close_max_age_seconds=_positive_integer(
            values, "QUANTBET_LIVE_CLOSE_MAX_AGE_SECONDS", "120"
        ),
        stale_quote_retry_policy=_stale_quote_retry_policy(values),
        model_training_interval_seconds=_positive_number(
            values, "QUANTBET_MODEL_TRAINING_INTERVAL_SECONDS", "60"
        ),
        model_training_max_scopes=_positive_integer(
            values, "QUANTBET_MODEL_TRAINING_MAX_SCOPES", "1"
        ),
        model_training_max_provider_requests=_positive_integer(
            values, "QUANTBET_MODEL_TRAINING_MAX_PROVIDER_REQUESTS", "2"
        ),
        model_training_max_wall_seconds=_positive_number(
            values, "QUANTBET_MODEL_TRAINING_MAX_WALL_SECONDS", "45"
        ),
        model_training_daily_limit=training_daily_limit,
        model_training_operational_reserve=training_operational_reserve,
        model_training_policy=training_policy,
        scheduler_tick_seconds=_positive_number(
            values, "QUANTBET_SCHEDULER_TICK_SECONDS", "5"
        ),
        shutdown_grace_seconds=_positive_number(
            values, "QUANTBET_SHUTDOWN_GRACE_SECONDS", "30"
        ),
        api_daily_limit=api_limit,
        api_reserve=api_reserve,
        api_timeout_seconds=_positive_number(values, "QUANTBET_API_TIMEOUT_SECONDS", "10"),
        database_startup_attempts=_positive_integer(
            values, "QUANTBET_DATABASE_STARTUP_ATTEMPTS", "12"
        ),
        database_startup_backoff_seconds=_positive_number(
            values, "QUANTBET_DATABASE_STARTUP_BACKOFF_SECONDS", "5"
        ),
        port=port,
    )


def _stale_quote_retry_policy(values: Mapping[str, str]) -> StaleQuoteRetryPolicy:
    initial = _positive_integer(
        values, "QUANTBET_STALE_QUOTE_INITIAL_RETRY_SECONDS", "120"
    )
    maximum = _positive_integer(
        values, "QUANTBET_STALE_QUOTE_MAX_RETRY_SECONDS", "900"
    )
    attempts = _positive_integer(values, "QUANTBET_STALE_QUOTE_MAX_ATTEMPTS", "5")
    horizon = _positive_integer(
        values, "QUANTBET_STALE_QUOTE_RETRY_HORIZON_SECONDS", "3600"
    )
    try:
        return StaleQuoteRetryPolicy(
            initial_interval=timedelta(seconds=initial),
            max_interval=timedelta(seconds=maximum),
            max_attempts=attempts,
            horizon=timedelta(seconds=horizon),
        )
    except ValueError as exc:
        raise ConfigError(f"Invalid stale quote retry configuration: {exc}") from exc


_RESULT_ENV = {
    "initial_delay_seconds": "QUANTBET_RESULT_INITIAL_DELAY_SECONDS",
    "poll_interval_seconds": "QUANTBET_RESULT_POLL_INTERVAL_SECONDS",
    "suspended_poll_interval_seconds": "QUANTBET_RESULT_SUSPENDED_POLL_INTERVAL_SECONDS",
    "postponed_poll_interval_seconds": "QUANTBET_RESULT_POSTPONED_POLL_INTERVAL_SECONDS",
    "finality_delay_seconds": "QUANTBET_RESULT_FINALITY_DELAY_SECONDS",
    "claim_lease_seconds": "QUANTBET_RESULT_CLAIM_LEASE_SECONDS",
    "claim_limit": "QUANTBET_RESULT_CLAIM_LIMIT",
    "correction_window_seconds": "QUANTBET_RESULT_CORRECTION_WINDOW_SECONDS",
}


def load_result_settlement_policy(
    environ: Mapping[str, str] | None = None,
) -> ResultSettlementPolicy:
    values = os.environ if environ is None else environ
    configured = [name for name in _RESULT_ENV.values() if values.get(name, "").strip()]
    if not configured:
        return ResultSettlementPolicy()
    missing = [name for name in _RESULT_ENV.values() if not values.get(name, "").strip()]
    if missing:
        raise ConfigError(f"Missing required result settlement configuration: {missing[0]}")
    parsed: dict[str, int] = {}
    for field_name, env_name in _RESULT_ENV.items():
        try:
            parsed[field_name] = int(values[env_name].strip())
        except ValueError as exc:
            raise ConfigError(f"{env_name} must be an integer") from exc
    try:
        return ResultSettlementPolicy(**parsed)
    except ValueError as exc:
        raise ConfigError(f"Invalid result settlement configuration: {exc}") from exc


_LIFECYCLE_ENV_NAMES = (
    "QUANTBET_PICK_MONITOR_INTERVAL_SECONDS",
    "QUANTBET_CURRENT_MAX_AGE_SECONDS",
    "QUANTBET_CLOSING_MAX_AGE_SECONDS",
)


def load_odds_lifecycle_policy(
    environ: Mapping[str, str] | None = None,
) -> OddsLifecyclePolicy:
    """Load complete lifecycle interpretation settings; partial input fails closed."""

    values = os.environ if environ is None else environ

    def positive(name: str) -> int:
        raw = values.get(name, "").strip()
        if not raw:
            raise ConfigError(f"Missing required odds lifecycle configuration: {name}")
        try:
            result = int(raw)
        except ValueError as exc:
            raise ConfigError(f"{name} must be an integer") from exc
        if result <= 0:
            raise ConfigError(f"{name} must be positive")
        return result

    return OddsLifecyclePolicy(
        monitoring_interval_seconds=positive("QUANTBET_PICK_MONITOR_INTERVAL_SECONDS"),
        current_max_age_seconds=positive("QUANTBET_CURRENT_MAX_AGE_SECONDS"),
        closing_max_age_seconds=positive("QUANTBET_CLOSING_MAX_AGE_SECONDS"),
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
