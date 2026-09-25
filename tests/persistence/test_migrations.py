from pathlib import Path

import pytest

from h2h.persistence.migrations import apply_migrations


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self._fetchall: list[tuple[str]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        self.connection.executed.append((sql, params))
        if sql == "SELECT version FROM schema_migrations":
            self._fetchall = [(version,) for version in self.connection.completed]
        elif sql.startswith("INSERT INTO schema_migrations"):
            self.connection.completed.add(params[0])

    def fetchall(self) -> list[tuple[str]]:
        return self._fetchall


class FakeConnection:
    def __init__(self, completed: set[str] | None = None) -> None:
        self.completed = completed or set()
        self.executed: list[tuple[str, object]] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


def test_apply_migrations_runs_pending_files_in_lexical_order(tmp_path: Path) -> None:
    (tmp_path / "002_second.sql").write_text("SELECT 2;", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "README.txt").write_text("ignored", encoding="utf-8")
    connection = FakeConnection()

    applied = apply_migrations(connection, tmp_path)

    assert applied == ("001_first.sql", "002_second.sql")
    assert "SELECT 1;" in [sql for sql, _ in connection.executed]
    assert "SELECT 2;" in [sql for sql, _ in connection.executed]


def test_apply_migrations_skips_already_recorded_files(tmp_path: Path) -> None:
    (tmp_path / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    connection = FakeConnection({"001_first.sql"})

    assert apply_migrations(connection, tmp_path) == ()
    assert "SELECT 1;" not in [sql for sql, _ in connection.executed]


def test_apply_migrations_requires_existing_directory(tmp_path: Path) -> None:
    connection = FakeConnection()

    with pytest.raises(FileNotFoundError):
        apply_migrations(connection, tmp_path / "missing")

    assert connection.executed == []


def test_apply_migrations_rejects_file_as_directory(tmp_path: Path) -> None:
    migration_file = tmp_path / "migration.sql"
    migration_file.write_text("SELECT 1;", encoding="utf-8")
    connection = FakeConnection()

    with pytest.raises(NotADirectoryError):
        apply_migrations(connection, migration_file)

    assert connection.executed == []


def test_task9_migration_has_bounded_tables_and_no_global_quote_fixture_fk() -> None:
    migration = (
        Path(__file__).parents[2] / "migrations" / "004_fixture_prediction_value_evaluation.sql"
    ).read_text(encoding="utf-8")

    for table in (
        "fixtures",
        "fixture_observations",
        "fixture_predictions",
        "value_evaluations",
    ):
        assert f"CREATE TABLE {table}" in migration
    assert "REFERENCES fixtures(fixture_id)" in migration
    quote_series_section = migration.split("ALTER TABLE quote_series", 1)[1].split(
        "ALTER TABLE quote_snapshots", 1
    )[0]
    assert "REFERENCES fixtures" not in quote_series_section


def test_task10_migration_has_decision_bankroll_and_pick_boundaries() -> None:
    migration = (
        Path(__file__).parents[2] / "migrations" / "005_pick_decision_risk_registration.sql"
    ).read_text(encoding="utf-8")
    for table in (
        "pick_policy_configurations",
        "bankroll_accounts",
        "pick_decisions",
        "registered_picks",
        "bankroll_ledger_entries",
    ):
        assert f"CREATE TABLE {table}" in migration
    assert "UNIQUE (fixture_id, market)" in migration
    assert "STAKE_RESERVED" in migration
    assert "ON DELETE RESTRICT" in migration


def test_task11_migration_has_monitoring_transition_and_closing_boundaries() -> None:
    migration = (
        Path(__file__).parents[2] / "migrations" / "006_pick_monitoring_odds_lifecycle.sql"
    ).read_text(encoding="utf-8")
    for table in (
        "pick_monitoring_states",
        "pick_monitoring_transitions",
        "pick_closing_finalizations",
    ):
        assert f"CREATE TABLE {table}" in migration
    assert "ODDS_LIFECYCLE_V1" in migration
    assert "idx_pick_monitoring_due" in migration
    assert "pick_closing_finalizations_immutable" in migration
    assert "ALTER TABLE quote_snapshots" in migration


def test_task12_migration_has_result_settlement_ledger_and_clv_boundaries() -> None:
    migration = (
        Path(__file__).parents[2] / "migrations" / "007_results_settlement_performance.sql"
    ).read_text(encoding="utf-8")
    for table in (
        "fixture_result_observations",
        "fixture_result_acquisition_states",
        "pick_settlement_events",
        "pick_realized_clv",
    ):
        assert f"CREATE TABLE {table}" in migration
    assert "uq_pick_one_normal_settlement" in migration
    assert "uq_bankroll_one_reservation_per_pick" in migration
    assert "bankroll_ledger_entries_append_only" in migration


def test_live_closing_proxy_migration_is_append_only_and_separate_from_bookmaker_quotes() -> None:
    migration = (
        Path(__file__).parents[2] / "migrations" / "015_live_closing_proxy.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE pick_live_close_observations" in migration
    assert "CREATE TABLE pick_live_close_finalizations" in migration
    assert "api-football-live" in migration
    assert "CLV_MARKET_PROXY_ODDS_RATIO_PPM_V1" in migration
    assert "append-only" in migration
    assert "quote_series" not in migration


def test_manual_closing_override_migration_is_auditable_and_targeted() -> None:
    migration = (
        Path(__file__).parents[2] / "migrations" / "016_manual_closing_overrides.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE pick_manual_closing_overrides" in migration
    assert "operator-manual-last-observed" in migration
    assert "manual closing overrides are append-only" in migration
    assert "Seattle" in migration
    assert "Real Salt Lake" in migration
    assert "America%Cali" in migration
    assert "América%Cali" in migration
    assert "ORDER BY q.observed_at DESC" in migration
    assert "ON CONFLICT DO NOTHING" in migration


def test_seattle_btts_no_manual_close_migration_is_exact_and_append_only() -> None:
    migration = (
        Path(__file__).parents[2]
        / "migrations"
        / "019_manual_close_seattle_btts_no.sql"
    ).read_text(encoding="utf-8")

    assert "r.market = 'BTTS'" in migration
    assert "r.selection = 'NO'" in migration
    assert "Seattle" in migration
    assert "Real Salt Lake" in migration
    assert "operator-manual-last-observed" in migration
    assert "ORDER BY q.observed_at DESC" in migration
    assert "pick_manual_closing_overrides" in migration
    assert "ON CONFLICT DO NOTHING" in migration


def test_opportunity_retry_reset_migration_is_narrow_and_transient_only() -> None:
    migration = (
        Path(__file__).parents[2]
        / "migrations"
        / "017_reset_opportunity_retry_backlog.sql"
    ).read_text(encoding="utf-8")

    assert "DELETE FROM production_item_failures" in migration
    assert "worker_name = 'opportunity'" in migration
    assert "last_error_class = 'OpportunityOddsUnavailableError'" in migration
    assert "registered_picks" not in migration
    assert "quote_snapshots" not in migration
    assert "pick_decisions" not in migration


def test_full_opportunity_backoff_flush_touches_only_transient_worker_state() -> None:
    migration = (
        Path(__file__).parents[2]
        / "migrations"
        / "018_flush_opportunity_operational_backoff.sql"
    ).read_text(encoding="utf-8")

    statements = "\n".join(
        line for line in migration.splitlines() if not line.lstrip().startswith("--")
    )
    assert "DELETE FROM production_item_failures" in statements
    assert "worker_name = 'opportunity'" in statements
    assert "last_error_class" not in statements
    assert "registered_picks" not in statements
    assert "quote_snapshots" not in statements
    assert "pick_decisions" not in statements
    assert "bankroll" not in statements


def test_usable_stale_quote_migration_extends_only_refresh_state_enum() -> None:
    migration = (
        Path(__file__).parents[2]
        / "migrations"
        / "020_usable_stale_quote_state.sql"
    ).read_text(encoding="utf-8")

    assert "USABLE_STALE" in migration
    assert "production_quote_refresh_states" in migration
    assert "registered_picks" not in migration
    assert "quote_snapshots" not in migration
    assert "pick_decisions" not in migration


def test_operator_state_migration_is_minimal_and_append_only() -> None:
    migration = (
        Path(__file__).parents[2] / "migrations" / "014_pick_operator_state.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE pick_operator_state_events" in migration
    assert "state IN ('PLAYED', 'SKIPPED')" in migration
    assert "request_id TEXT NOT NULL UNIQUE" in migration
    assert "append-only" in migration
    assert "UNREPORTED" not in migration
    assert "reason" not in migration.casefold()
    assert "bookmaker" not in migration.casefold()


def test_research_exposure_signal_migration_is_append_only_and_bankroll_free() -> None:
    migration = (
        Path(__file__).parents[2]
        / "migrations"
        / "021_research_exposure_blocked_signals.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE research_exposure_blocked_signals" in migration
    assert "MAX_OPEN_EXPOSURE_EXCEEDED" in migration
    assert "RAILWAY_LOG_BACKFILL" in migration
    assert "LIVE_GATE" in migration
    assert "research_exposure_blocked_signals_append_only" in migration
    assert "STAKE_RESERVED" not in migration
    assert "INSERT INTO registered_picks" not in migration
