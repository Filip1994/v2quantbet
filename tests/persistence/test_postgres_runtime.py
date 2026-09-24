from datetime import UTC, datetime, timedelta

from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy


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
                None,
                None,
                None,
                None,
                None,
                None,
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
                None,
                None,
                None,
                None,
                None,
                None,
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
                None,
                None,
                None,
                None,
                None,
                None,
                None,
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
                None,
                None,
                None,
                None,
                None,
                None,
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
        item_limit=2,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=StaleQuoteRetryPolicy(
            timedelta(minutes=2), timedelta(minutes=15), 5, timedelta(hours=1)
        ),
    )

    assert tuple(item.fixture_id for item in selection.due_fixtures) == (
        "api-football:1",
    )
    assert selection.eligible_fixture_count == 3
    assert selection.phase_i_excluded_count == 1
    assert selection.waiting_for_window_count == 1
    assert selection.waiting_for_refresh_count == 1
    assert "f.league_id =" not in cursor.query
    assert cursor.parameters == (
        8,
        8,
        8,
        now,
        now + timedelta(hours=72),
        ["NS"],
        now,
        False,
        now,
        None,
        None,
        None,
        9,
    )
    assert "LIMIT %s" in cursor.query
    assert "ORDER BY latest.kickoff_at, f.fixture_id" in cursor.query


class OpportunityOddsUnavailableError(RuntimeError):
    pass


def test_opportunity_no_odds_failure_starts_with_ten_minute_retry() -> None:
    failed_at = datetime(2026, 9, 24, 13, tzinfo=UTC)
    cursor = FakeCursor([])
    repository = PostgreSQLRuntimeRepository(connect=lambda: FakeConnection(cursor))

    repository.record_item_failure(
        "opportunity",
        "api-football:123",
        OpportunityOddsUnavailableError("no odds"),
        failed_at=failed_at,
    )

    assert cursor.parameters[3] == failed_at + timedelta(minutes=10)
    assert cursor.parameters[4] == "OpportunityOddsUnavailableError"
    assert "interval '10 minutes'" in cursor.query
    assert "interval '1 hour'" in cursor.query


def test_non_odds_item_failure_keeps_fast_generic_retry() -> None:
    failed_at = datetime(2026, 9, 24, 13, tzinfo=UTC)
    cursor = FakeCursor([])
    repository = PostgreSQLRuntimeRepository(connect=lambda: FakeConnection(cursor))

    repository.record_item_failure(
        "opportunity",
        "api-football:123",
        RuntimeError("transient"),
        failed_at=failed_at,
    )

    assert cursor.parameters[3] == failed_at + timedelta(seconds=5)
    assert cursor.parameters[4] == "RuntimeError"
