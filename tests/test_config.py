import pytest

from h2h.config import (
    ApplicationSettings,
    ConfigError,
    load_config,
    load_odds_lifecycle_policy,
    load_registration_policy_config,
    load_settings,
)


def _set_valid_config(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "info")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("ODDS_API_KEY", "test-key")


def test_load_config_reads_required_values(monkeypatch):
    _set_valid_config(monkeypatch)

    config = load_config()

    assert config.app_env == "test"
    assert config.log_level == "INFO"
    assert config.database_url == "postgresql://example"
    assert config.odds_api_key == "test-key"


def test_load_config_rejects_missing_required_value(monkeypatch):
    _set_valid_config(monkeypatch)
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(ConfigError, match="DATABASE_URL"):
        load_config()


def test_load_config_rejects_invalid_log_level(monkeypatch):
    _set_valid_config(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "NOPE")

    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        load_config()


def test_config_repr_redacts_secrets(monkeypatch):
    _set_valid_config(monkeypatch)

    rendered = repr(load_config())

    assert "postgresql://example" not in rendered
    assert "test-key" not in rendered
    assert "[REDACTED]" in rendered


def test_load_settings_reads_api_key_and_database_path() -> None:
    settings = load_settings(
        {
            "API_FOOTBALL_KEY": "  test-football-key  ",
            "QUANTBET_DATABASE_PATH": "tmp/quotes.sqlite3",
        }
    )

    assert isinstance(settings, ApplicationSettings)
    assert settings.api_football_key == "test-football-key"
    assert settings.database_path.as_posix() == "tmp/quotes.sqlite3"
    assert settings.database_url is None


def test_load_settings_reads_optional_database_url() -> None:
    settings = load_settings(
        {
            "API_FOOTBALL_KEY": "test-football-key",
            "DATABASE_URL": " postgresql://example/quantbet ",
        }
    )

    assert settings.database_url == "postgresql://example/quantbet"


def test_load_settings_uses_default_database_path() -> None:
    settings = load_settings({"API_FOOTBALL_KEY": "test-football-key"})

    assert settings.database_path.as_posix() == "data/quantbet.sqlite3"


@pytest.mark.parametrize("environment", [{}, {"API_FOOTBALL_KEY": "   "}])
def test_load_settings_requires_api_football_key(environment) -> None:
    with pytest.raises(ConfigError, match="API_FOOTBALL_KEY"):
        load_settings(environment)


def test_application_settings_repr_redacts_api_key_and_database_url() -> None:
    settings = ApplicationSettings(
        database_path="quotes.sqlite3",
        api_football_key="secret",
        database_url="postgresql://secret-host/quantbet",
    )

    rendered = repr(settings)

    assert "secret" not in rendered
    assert "postgresql://secret-host/quantbet" not in rendered
    assert "[REDACTED]" in rendered


def registration_environment():
    return {
        "QUANTBET_ALLOWED_MARKET_SELECTIONS": "OU_25/OVER,OU_25/UNDER,BTTS/YES,BTTS/NO",
        "QUANTBET_ALLOWED_DEVIG_METHODS": "PROPORTIONAL_TWO_WAY_V1",
        "QUANTBET_ALLOWED_FIXTURE_STATUSES": "NS",
        "QUANTBET_MINIMUM_EDGE": "0.03",
        "QUANTBET_MINIMUM_EXPECTED_VALUE": "0.02",
        "QUANTBET_MINIMUM_ODDS": "1.40",
        "QUANTBET_MAXIMUM_ODDS": "3.50",
        "QUANTBET_MAXIMUM_QUOTE_AGE_SECONDS": "300",
        "QUANTBET_MINIMUM_TIME_TO_KICKOFF_SECONDS": "600",
        "QUANTBET_BANKROLL_ACCOUNT_ID": "quantbet-pilot-rsd",
        "QUANTBET_CURRENCY": "RSD",
        "QUANTBET_INITIAL_BANKROLL_MINOR": "3000000",
        "QUANTBET_FIXED_STAKE_MINOR": "30000",
        "QUANTBET_MAX_STAKE_PER_PICK_MINOR": "30000",
        "QUANTBET_MAX_OPEN_EXPOSURE_MINOR": "300000",
    }


def test_load_registration_policy_config_reads_explicit_pilot_values() -> None:
    policy = load_registration_policy_config(registration_environment())
    assert str(policy.minimum_edge) == "0.03"
    assert policy.initial_bankroll_minor == 3_000_000
    assert policy.fixed_stake_minor == 30_000
    assert policy.allowed_fixture_statuses == ("NS",)


def test_partial_registration_policy_fails_clearly() -> None:
    environment = registration_environment()
    del environment["QUANTBET_MINIMUM_EDGE"]
    with pytest.raises(ConfigError, match="QUANTBET_MINIMUM_EDGE"):
        load_registration_policy_config(environment)


def test_load_settings_parses_policy_only_when_registration_is_configured() -> None:
    environment = registration_environment()
    environment["API_FOOTBALL_KEY"] = "test-key"
    settings = load_settings(environment)
    assert settings.registration_policy is not None
    assert settings.registration_policy.fingerprint.startswith("pick-policy-config-v1:")


def lifecycle_environment():
    return {
        "QUANTBET_PICK_MONITOR_INTERVAL_SECONDS": "300",
        "QUANTBET_CURRENT_MAX_AGE_SECONDS": "600",
        "QUANTBET_CLOSING_MAX_AGE_SECONDS": "900",
    }


def test_load_odds_lifecycle_policy_requires_complete_explicit_values() -> None:
    policy = load_odds_lifecycle_policy(lifecycle_environment())
    assert policy.monitoring_interval_seconds == 300
    partial = lifecycle_environment()
    del partial["QUANTBET_CLOSING_MAX_AGE_SECONDS"]
    with pytest.raises(ConfigError, match="QUANTBET_CLOSING_MAX_AGE_SECONDS"):
        load_odds_lifecycle_policy(partial)


def test_load_settings_validates_bulletin_timezone_and_lifecycle() -> None:
    environment = lifecycle_environment()
    environment.update(
        {
            "API_FOOTBALL_KEY": "test-key",
            "QUANTBET_BULLETIN_TIMEZONE": "Europe/Belgrade",
        }
    )
    settings = load_settings(environment)
    assert settings.odds_lifecycle_policy is not None
    assert settings.bulletin_timezone.key == "Europe/Belgrade"
    environment["QUANTBET_BULLETIN_TIMEZONE"] = "Not/A_Zone"
    with pytest.raises(ConfigError, match="IANA"):
        load_settings(environment)
