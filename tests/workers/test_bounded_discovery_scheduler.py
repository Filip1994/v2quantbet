from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from h2h.persistence.fixtures import FixturePersistenceConflictError
from h2h.use_cases.api_football_fixture_discovery import ApiFootballFixtureDiscovery
from h2h.use_cases.durable_fixture_discovery import DurableFixtureDiscovery
from h2h.use_cases.scoped_fixture_discovery import ScopedFixtureDiscovery
from h2h.workers.orchestrator import ProductionOrchestrator, ScheduledJob


class RuntimeFake:
    def worker_started(self, *_args: object, **_kwargs: object) -> None:
        return

    def worker_succeeded(self, *_args: object, **_kwargs: object) -> None:
        return

    def worker_failed(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("no worker should fail")


class FixtureRepositoryFake:
    def __init__(self) -> None:
        self.fixture_ids: list[str] = []

    def record_discovery(self, fixture, *, observed_at):
        self.fixture_ids.append(fixture.fixture_id)
        return fixture


class DeterministicStop:
    def __init__(self, now: list[datetime]) -> None:
        self._now = now
        self._stopped = False
        self.done = lambda: False

    def is_set(self) -> bool:
        return self._stopped

    def set(self) -> None:
        self._stopped = True

    def wait(self, seconds: float) -> None:
        self._now[0] += timedelta(seconds=seconds)
        if self.done():
            self.set()


def _payload(fixture_date: date) -> dict[str, object]:
    fixture_id = int(fixture_date.strftime("%m%d"))
    return {
        "fixture": {
            "id": fixture_id,
            "date": datetime.combine(fixture_date, datetime.min.time(), tzinfo=UTC).isoformat(),
            "status": {"short": "NS"},
        },
        "league": {
            "id": 253,
            "name": "Major League Soccer",
            "country": "USA",
            "type": "league",
            "season": 2026,
        },
        "teams": {
            "home": {"id": fixture_id * 2, "name": f"Home {fixture_id}"},
            "away": {"id": fixture_id * 2 + 1, "name": f"Away {fixture_id}"},
        },
    }


def test_cold_start_is_persisted_in_bounded_units_without_starving_scheduler() -> None:
    now = [datetime(2026, 9, 1, tzinfo=UTC)]
    start = now[0]
    end = start + timedelta(hours=504)
    client = Mock()
    client.fetch_fixtures_for_date.side_effect = lambda *, fixture_date: {
        "errors": [],
        "response": [_payload(fixture_date)],
    }
    repository = FixtureRepositoryFake()
    durable = DurableFixtureDiscovery(
        ScopedFixtureDiscovery(ApiFootballFixtureDiscovery(client, clock=lambda: now[0])),
        repository,
        clock=lambda: now[0],
    )
    stop = DeterministicStop(now)
    discovery_runs: list[datetime] = []
    opportunity_runs: list[datetime] = []
    monitoring_runs: list[datetime] = []
    results_runs: list[datetime] = []

    def run_discovery() -> None:
        discovery_runs.append(now[0])
        persisted = durable.discover(start, end)
        assert len(persisted) <= 10

    jobs = (
        ScheduledJob(
            "discovery",
            900,
            run_discovery,
            has_pending_work=lambda: durable.has_pending,
        ),
        ScheduledJob("opportunity", 3, lambda: opportunity_runs.append(now[0])),
        ScheduledJob("monitoring", 4, lambda: monitoring_runs.append(now[0])),
        ScheduledJob("results", 5, lambda: results_runs.append(now[0])),
    )
    stop.done = lambda: len(repository.fixture_ids) == 22 and not durable.has_pending

    completed = ProductionOrchestrator(
        jobs,
        RuntimeFake(),
        instance_id="test",
        stop=stop,  # type: ignore[arg-type]
        tick_seconds=1,
        leader_healthy=lambda: True,
        clock=lambda: now[0],
    ).run_forever()

    assert completed is True
    assert len(discovery_runs) == 13
    assert opportunity_runs == [
        start + timedelta(seconds=value) for value in (0, 3, 6, 9, 12)
    ]
    assert monitoring_runs == [
        start + timedelta(seconds=value) for value in (0, 4, 8, 12)
    ]
    assert results_runs == [start + timedelta(seconds=value) for value in (0, 5, 10)]
    assert len(repository.fixture_ids) == len(set(repository.fixture_ids)) == 22
    assert client.fetch_fixtures_for_date.call_count == 22



def test_conflicting_fixture_is_quarantined_without_stopping_discovery_batch() -> None:
    now = datetime(2026, 9, 24, 14, tzinfo=UTC)

    def item(fixture_id: str, provider_fixture_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            fixture_id=fixture_id,
            provider="api-football",
            provider_fixture_id=provider_fixture_id,
            competition_id=253,
            season=2026,
            provider_home_team_id=10,
            provider_away_team_id=20,
        )

    good_before = item("api-football:1", "1")
    poisoned = item("api-football:2", "2")
    good_after = item("api-football:3", "3")
    attempted: list[str] = []
    persisted_ids: list[str] = []

    class ConflictRepository:
        def record_discovery(self, fixture, *, observed_at):
            attempted.append(fixture.fixture_id)
            if fixture.fixture_id == poisoned.fixture_id:
                raise FixturePersistenceConflictError("immutable fixture identity conflicts")
            persisted_ids.append(fixture.fixture_id)
            return fixture

    source = SimpleNamespace(
        discover=lambda _start, _end: (good_before, poisoned, good_after),
        has_pending=False,
    )
    durable = DurableFixtureDiscovery(
        source,
        ConflictRepository(),
        clock=lambda: now,
        max_per_call=3,
    )

    result = durable.discover(now, now + timedelta(days=1))

    assert [fixture.fixture_id for fixture in result] == [
        good_before.fixture_id,
        good_after.fixture_id,
    ]
    assert attempted == [
        good_before.fixture_id,
        poisoned.fixture_id,
        good_after.fixture_id,
    ]
    assert persisted_ids == [good_before.fixture_id, good_after.fixture_id]
    assert durable.has_pending is False
