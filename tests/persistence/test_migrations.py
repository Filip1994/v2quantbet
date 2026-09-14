from pathlib import Path

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
