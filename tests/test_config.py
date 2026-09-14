import pytest

from h2h.config import ApplicationSettings, ConfigError, load_config, load_settings


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


def test_load_settings_uses_default_database_path() -> None:
    settings = load_settings({"API_FOOTBALL_KEY": "test-football-key"})

    assert settings.database_path.as_posix() == "data/quantbet.sqlite3"


@pytest.mark.parametrize("environment", [{}, {"API_FOOTBALL_KEY": "   "}])
def test_load_settings_requires_api_football_key(environment) -> None:
    with pytest.raises(ConfigError, match="API_FOOTBALL_KEY"):
        load_settings(environment)


def test_application_settings_repr_redacts_api_key() -> None:
    settings = ApplicationSettings(database_path="quotes.sqlite3", api_football_key="secret")

    rendered = repr(settings)

    assert "secret" not in rendered
    assert "[REDACTED]" in rendered
