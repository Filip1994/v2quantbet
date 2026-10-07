from pathlib import Path


def test_kellylab_migration_is_isolated_and_append_only() -> None:
    migration = (
        Path(__file__).parents[2]
        / "migrations"
        / "065_kellylab_shadow_portfolio.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE kellylab_portfolios" in migration
    assert "CREATE TABLE kellylab_picks" in migration
    assert "KELLYLAB_RESEARCH_V1" in migration
    assert "starting_bankroll_minor" in migration
    assert "calibration_snapshot JSONB NOT NULL" in migration
    assert "bankroll_before_minor" in migration
    assert "stake_minor BIGINT NOT NULL CHECK (stake_minor >= 0)" in migration
    assert "KellyLab facts are append-only" in migration
    assert "INSERT INTO research_signals" not in migration
    assert "UPDATE research_signals" not in migration
    assert "INSERT INTO registered_picks" not in migration
    assert "bankroll_ledger_entries" not in migration
