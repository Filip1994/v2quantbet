from datetime import UTC, datetime, timedelta

from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository


class FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.query = ""
        self.parameters: tuple[object, ...] = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query: str, parameters: tuple[object, ...]) -> None:
        self.query = query
        self.parameters = parameters

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor


def test_opportunity_selection_uses_phase_i_policy_without_league_allowlist() -> None:
    now = datetime(2026, 9, 22, 12, tzinfo=UTC)
    cursor = FakeCursor(
        [
            (
                "api-football:1",
                1,
                140,
                2026,
                now + timedelta(hours=2),
                "Spain",
                "La Liga",
                "League",
                None,
            ),
            (
                "api-football:2",
                2,
                39,
                2026,
                now + timedelta(hours=100),
                "England",
                "Premier League",
                "League",
                None,
            ),
            (
                "api-football:3",
                3,
                135,
                2026,
                now + timedelta(hours=2),
                "Italy",
                "Serie A",
                "League",
                now,
            ),
            (
                "api-football:4",
                4,
                41,
                2026,
                now + timedelta(hours=2),
                "England",
                "League Two",
                "League",
                None,
            ),
        ]
    )
    repository = PostgreSQLRuntimeRepository(
        connect=lambda: FakeConnection(cursor)
    )

    selection = repository.select_opportunity_fixtures(
        bookmaker_id=8,
        allowed_statuses=("NS",),
        now=now,
    )

    assert tuple(item.fixture_id for item in selection.due_fixtures) == (
        "api-football:1",
    )
    assert selection.eligible_fixture_count == 3
    assert selection.phase_i_excluded_count == 1
    assert selection.waiting_for_window_count == 1
    assert selection.waiting_for_refresh_count == 1
    assert "f.league_id =" not in cursor.query
    assert cursor.parameters == (8, now, ["NS"])
