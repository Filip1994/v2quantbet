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
