from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from h2h.odds import ApiBudgetExceededError
from h2h.persistence.postgres_runtime import (
    CompleteMarketQuoteState,
    OpportunityFixture,
    OpportunitySelection,
    PostgreSQLRuntimeRepository,
    QuoteRefreshState,
)
from h2h.workers.opportunity import OpportunityWorker
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy


NOW = datetime(2026, 9, 23, 12, tzinfo=UTC)
POLICY = StaleQuoteRetryPolicy(timedelta(minutes=2), timedelta(minutes=8), 5, timedelta(minutes=30))


class SelectionCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, _parameters):
        self.query = query

    def fetchall(self):
        return self.rows


class SelectionConnection:
    def __init__(self, rows):
        self._cursor = SelectionCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self._cursor


def selection_row(
    *,
    kickoff_at=NOW + timedelta(hours=4),
    last_captured_at=NOW,
    freshness_state=None,
    stale_attempt_count=None,
    stale_next_retry_at=None,
    refresh_last_attempt_at=None,
    observed_at=NOW,
):
    return (
        "api-football:1549793",
        1549793,
        239,
        2026,
        kickoff_at,
        "Colombia",
        "Primera A",
        "League",
        last_captured_at,
        None,
        freshness_state,
        stale_attempt_count,
        stale_next_retry_at,
        refresh_last_attempt_at,
        observed_at,
        last_captured_at,
    )


def select(row):
    repository = PostgreSQLRuntimeRepository(connect=lambda: SelectionConnection([row]))
    return repository.select_opportunity_fixtures(
        bookmaker_id=8,
        allowed_statuses=("NS",),
        now=NOW,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=POLICY,
    )


def test_selection_filters_non_ready_work_before_the_batch_limit() -> None:
    connection = SelectionConnection([])
    repository = PostgreSQLRuntimeRepository(connect=lambda: connection)

    repository.select_opportunity_fixtures(
        bookmaker_id=8,
        allowed_statuses=("NS",),
        now=NOW,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=POLICY,
    )

    query = connection._cursor.query
    assert "JOIN model_coverage_scopes coverage" in query
    assert "coverage.active_model_version_id IS NOT NULL" in query
    assert "failures.next_retry_at IS NULL OR failures.next_retry_at <= %s" in query
    assert query.index("coverage.active_model_version_id IS NOT NULL") < query.index("LIMIT %s")
    assert query.index("failures.next_retry_at IS NULL") < query.index("LIMIT %s")


def test_fresh_capture_with_stale_observation_bypasses_normal_cadence() -> None:
    result = select(selection_row(observed_at=NOW - timedelta(minutes=30)))

    assert result.waiting_for_refresh_count == 0
    assert result.due_fixtures[0].stale_retry is True


def test_fresh_observation_uses_normal_captured_at_cadence() -> None:
    result = select(selection_row(observed_at=NOW - timedelta(minutes=1)))

    assert result.due_fixtures == ()
    assert result.waiting_for_refresh_count == 1


def test_persisted_stale_retry_waits_until_due_without_tight_loop() -> None:
    waiting = select(
        selection_row(
            freshness_state="STALE",
            stale_attempt_count=1,
            stale_next_retry_at=NOW + timedelta(minutes=2),
            observed_at=NOW - timedelta(minutes=30),
        )
    )
    due = select(
        selection_row(
            freshness_state="STALE",
            stale_attempt_count=1,
            stale_next_retry_at=NOW,
            observed_at=NOW - timedelta(minutes=30),
        )
    )

    assert waiting.due_fixtures == ()
    assert waiting.waiting_for_refresh_count == 1
    assert due.due_fixtures[0].stale_retry is True


def test_due_stale_retry_can_be_selected_independently_of_normal_cursor() -> None:
    row = selection_row(
        freshness_state="STALE",
        stale_attempt_count=1,
        stale_next_retry_at=NOW,
        observed_at=NOW - timedelta(minutes=30),
    )
    repository = PostgreSQLRuntimeRepository(connect=lambda: SelectionConnection([row]))

    result = repository.select_due_stale_quote_retries(
        bookmaker_id=8,
        allowed_statuses=("NS",),
        now=NOW,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=POLICY,
    )

    assert result.due_fixtures[0].fixture_id == "api-football:1549793"
    assert result.due_fixtures[0].stale_retry is True


def test_exhausted_stale_path_uses_last_attempt_for_normal_cadence() -> None:
    result = select(
        selection_row(
            last_captured_at=NOW - timedelta(hours=3),
            freshness_state="STALE",
            stale_attempt_count=5,
            stale_next_retry_at=None,
            refresh_last_attempt_at=NOW,
            observed_at=NOW - timedelta(hours=4),
        )
    )

    assert result.due_fixtures == ()
    assert result.waiting_for_refresh_count == 1


def test_stale_retry_stops_inside_minimum_kickoff_window() -> None:
    result = select(
        selection_row(
            kickoff_at=NOW + timedelta(minutes=9),
            freshness_state="STALE",
            stale_attempt_count=1,
            stale_next_retry_at=NOW,
            observed_at=NOW - timedelta(minutes=30),
        )
    )

    assert result.due_fixtures == ()
    assert result.waiting_for_window_count == 1
    assert result.stale_retries_stopped == 1


def test_retry_policy_exponentially_backs_off_and_is_bounded() -> None:
    delays = []
    for attempt in range(1, 6):
        next_at = POLICY.next_retry_at(
            stale_attempt_count=attempt,
            first_stale_at=NOW,
            attempted_at=NOW,
        )
        delays.append(None if next_at is None else next_at - NOW)

    assert delays == [
        timedelta(minutes=2),
        timedelta(minutes=4),
        timedelta(minutes=8),
        timedelta(minutes=8),
        None,
    ]


class WorkerRepository:
    def __init__(self, fixture, market_states):
        self.fixture = fixture
        self.market_states = market_states
        self.state: QuoteRefreshState | None = None
        self.evaluation_snapshots = ("snapshot-btts-no",)

    def select_opportunity_fixtures(self, **_kwargs):
        return OpportunitySelection(1, 0, 0, 0, (self.fixture,))

    def latest_complete_market_states(self, *_args):
        return self.market_states

    def record_quote_refresh_state(
        self,
        _fixture_id,
        _bookmaker_id,
        *,
        freshness_state,
        attempted_at,
        latest_observed_at,
        latest_captured_at,
        stale_retry_policy,
    ):
        prior_stale = self.state is not None and self.state.freshness_state == "STALE"
        count = self.state.stale_attempt_count + 1 if prior_stale else 1
        first = self.state.first_stale_at if prior_stale else attempted_at
        if freshness_state != "STALE":
            count = 0
            first = None
            next_at = None
        else:
            next_at = stale_retry_policy.next_retry_at(
                stale_attempt_count=count,
                first_stale_at=first,
                attempted_at=attempted_at,
            )
        self.state = QuoteRefreshState(
            freshness_state,
            count,
            first,
            attempted_at,
            next_at,
            latest_observed_at,
            latest_captured_at,
        )
        return self.state

    def latest_complete_snapshot_ids(self, *_args):
        return self.evaluation_snapshots

    def clear_item_failure(self, *_args):
        return None

    def record_item_failures(self, _failures):
        return None


def fixture(*, stale_retry=False, prior_state=None):
    return OpportunityFixture(
        "api-football:1549793",
        SimpleNamespace(fixture_id="api-football:1549793"),
        239,
        2026,
        NOW + timedelta(hours=4),
        NOW,
        quote_freshness_state=prior_state,
        stale_retry=stale_retry,
    )


def build_worker(repository, source, *, clock=lambda: NOW):
    evaluations = []
    decisions = []

    def evaluate(_prediction_id, snapshot_id):
        evaluations.append(snapshot_id)
        return SimpleNamespace(
            evaluation_id=f"evaluation:{snapshot_id}",
            bookmaker_id=8,
            market=SimpleNamespace(value="BTTS"),
            selected_selection=SimpleNamespace(value="YES"),
            selected_odd=1.5,
            edge=-0.1,
            expected_value=-0.1,
        )

    def register(evaluation_id, _request_id):
        decisions.append(evaluation_id)
        return SimpleNamespace(pick=None)

    worker = OpportunityWorker(
        repository,
        source,
        SimpleNamespace(ingest=lambda _quotes: 0),
        SimpleNamespace(execute=lambda _fixture_id: SimpleNamespace(prediction_id="prediction")),
        SimpleNamespace(execute=evaluate),
        SimpleNamespace(
            execute=register,
            preliminary_rejection_codes=lambda _evaluation_id: ("EDGE_BELOW_MINIMUM",),
        ),
        bookmaker_id=8,
        allowed_statuses=("NS",),
        ensure_model_available=lambda _fixture: None,
        should_stop=lambda: False,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=POLICY,
        clock=clock,
    )
    return worker, evaluations, decisions


def test_repeated_stale_payload_is_replay_safe_and_schedules_backoff() -> None:
    stale_market = CompleteMarketQuoteState(
        "BTTS", NOW - timedelta(minutes=30), NOW, "api-football"
    )
    repository = WorkerRepository(fixture(), (stale_market,))
    source = SimpleNamespace(fetch_quotes=lambda **_kwargs: (SimpleNamespace(),))
    worker, evaluations, decisions = build_worker(repository, source)

    first = worker.run_once()
    repository.fixture = fixture(stale_retry=True, prior_state="STALE")
    second = worker.run_once()

    assert first.stale_market_count == second.stale_market_count == 1
    assert repository.state is not None
    assert repository.state.stale_attempt_count == 2
    assert repository.state.next_retry_at == NOW + timedelta(minutes=4)
    assert evaluations == ["snapshot-btts-no", "snapshot-btts-no"]
    assert decisions == []


def test_later_fresh_payload_clears_stale_state_automatically() -> None:
    repository = WorkerRepository(
        fixture(stale_retry=True, prior_state="STALE"),
        (CompleteMarketQuoteState("BTTS", NOW - timedelta(minutes=1), NOW, "api-football"),),
    )
    repository.state = QuoteRefreshState(
        "STALE", 2, NOW - timedelta(minutes=10), NOW - timedelta(minutes=4), NOW, NOW, NOW
    )
    worker, _evaluations, _decisions = build_worker(
        repository, SimpleNamespace(fetch_quotes=lambda **_kwargs: (SimpleNamespace(),))
    )

    result = worker.run_once()

    assert result.stale_retries_cleared == 1
    assert repository.state is not None
    assert repository.state.freshness_state == "FRESH"
    assert repository.state.stale_attempt_count == 0
    assert repository.state.next_retry_at is None


def test_budget_exhaustion_suppresses_stale_retry_before_persistence() -> None:
    repository = WorkerRepository(fixture(stale_retry=True, prior_state="STALE"), ())

    def exhausted(**_kwargs):
        raise ApiBudgetExceededError("exhausted")

    worker, _evaluations, _decisions = build_worker(
        repository, SimpleNamespace(fetch_quotes=exhausted)
    )

    result = worker.run_once()

    assert result.budget_exhausted is True
    assert result.stale_retries_requested == 1
    assert result.stale_retries_suppressed_by_budget == 1
    assert repository.state is None


def test_latest_snapshot_query_selects_only_latest_capture_for_chosen_observation() -> None:
    connection = SelectionConnection([])
    repository = PostgreSQLRuntimeRepository(connect=lambda: connection)

    assert repository.latest_complete_snapshot_ids("api-football:1549793", 8) == ()
    assert "q.captured_at = c.captured_at" in connection._cursor.query


def test_exact_market_snapshot_query_deduplicates_repeated_provider_observation() -> None:
    connection = SelectionConnection([])
    repository = PostgreSQLRuntimeRepository(connect=lambda: connection)

    assert (
        repository.snapshot_ids_for_market_observation(
            "api-football:1549793",
            8,
            "BTTS",
            NOW,
            "api-football",
        )
        == ()
    )
    assert "DISTINCT ON (s.selection)" in connection._cursor.query
    assert "q.captured_at DESC" in connection._cursor.query


def test_complete_market_query_never_combines_different_observation_times() -> None:
    connection = SelectionConnection([])
    repository = PostgreSQLRuntimeRepository(connect=lambda: connection)

    assert repository.latest_complete_market_states("api-football:1549793", 8) == ()
    query = connection._cursor.query
    assert "GROUP BY s.market, q.observed_at, q.source" in query
    assert "HAVING COUNT(DISTINCT s.selection) = 2" in query
