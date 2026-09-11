import pytest

from h2h.config import ConfigError, load_config


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
