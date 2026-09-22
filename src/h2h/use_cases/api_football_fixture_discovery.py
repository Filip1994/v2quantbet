"""API-Football implementation of the provider-neutral fixture discovery port."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, time, timedelta

from h2h.domain.fixture import Fixture
from h2h.odds.api_football_client import ApiFootballClient
from h2h.use_cases.api_football_fixture_adapter import ApiFootballFixtureAdapter


class ApiFootballFixtureDiscovery:
    """Discover canonical fixtures through API-Football's fixtures endpoint."""

    _NEAR_HORIZON = timedelta(hours=72)
    _NEAR_REFRESH = timedelta(hours=6)
    _FAR_REFRESH = timedelta(hours=24)
    _FAILURE_RETRY = timedelta(hours=1)

    def __init__(
        self,
        client: ApiFootballClient,
        adapter: ApiFootballFixtureAdapter | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._adapter = adapter or ApiFootballFixtureAdapter()
        self._clock = clock
        self._cache: dict[date, tuple[datetime, tuple[Fixture, ...]]] = {}
        self._pending: dict[date, tuple[datetime, tuple[Fixture, ...]]] = {}
        self._retry_after: dict[date, datetime] = {}

    def discover(self, start_at: datetime, end_at: datetime) -> tuple[Fixture, ...]:
        """Fetch and adapt fixtures, retaining only kickoffs inside the requested window."""
        start_utc = self._utc(start_at, "start_at")
        end_utc = self._utc(end_at, "end_at")
        if start_utc >= end_utc:
            raise ValueError("start_at must be before end_at")
        now = self._utc(self._clock(), "clock")
        dates = self._dates(start_utc, end_utc)
        active = set(dates)
        self._cache = {day: cached for day, cached in self._cache.items() if day in active}
        self._pending = {day: pending for day, pending in self._pending.items() if day in active}
        self._retry_after = {
            day: retry_at for day, retry_at in self._retry_after.items() if day in active
        }
        due = tuple(day for day in dates if self._refresh_due(day, now))
        blocked = tuple(
            day for day in due if day not in self._pending and self._retry_after.get(day, now) > now
        )
        if blocked:
            day = blocked[0]
            raise DateShardDiscoveryError(
                f"fixture date shard {day.isoformat()} retry deferred until "
                f"{self._retry_after[day].isoformat()}"
            )

        for day in due:
            if day in self._pending:
                continue
            try:
                payload = self._client.fetch_fixtures_for_date(fixture_date=day)
                fixtures = self._adapt_payload(payload)
            except Exception as exc:
                self._retry_after[day] = now + self._FAILURE_RETRY
                raise DateShardDiscoveryError(
                    f"fixture date shard {day.isoformat()} failed"
                ) from exc
            self._pending[day] = (now, fixtures)
            self._retry_after.pop(day, None)

        for day in due:
            self._cache[day] = self._pending.pop(day)

        discovered: dict[str, Fixture] = {}
        for day in dates:
            for fixture in self._cache[day][1]:
                if not start_utc <= fixture.kickoff_at <= end_utc:
                    continue
                previous = discovered.get(fixture.fixture_id)
                if previous is not None and previous != fixture:
                    raise ValueError(f"conflicting duplicate fixture: {fixture.fixture_id}")
                discovered[fixture.fixture_id] = fixture
        return tuple(
            sorted(discovered.values(), key=lambda item: (item.kickoff_at, item.fixture_id))
        )

    @staticmethod
    def _utc(value: datetime, field: str) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError(f"{field} must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field} must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _dates(start_at: datetime, end_at: datetime) -> tuple[date, ...]:
        count = (end_at.date() - start_at.date()).days
        return tuple(start_at.date() + timedelta(days=offset) for offset in range(count + 1))

    def _refresh_due(self, day: date, now: datetime) -> bool:
        cached = self._cache.get(day)
        if cached is None:
            return True
        fetched_at, _fixtures = cached
        shard_start = datetime.combine(day, time.min, tzinfo=UTC)
        refresh = (
            self._NEAR_REFRESH
            if shard_start <= now + self._NEAR_HORIZON
            else self._FAR_REFRESH
        )
        return fetched_at + refresh <= now

    def _adapt_payload(self, payload: Mapping[str, object]) -> tuple[Fixture, ...]:
        if not isinstance(payload, Mapping):
            raise TypeError("API-Football fixtures response must be an object")
        errors = payload.get("errors")
        if errors:
            raise RuntimeError(f"API-Football returned errors: {errors}")
        response = payload.get("response", [])
        if not isinstance(response, list):
            raise TypeError("API-Football response must be a list")

        fixtures: list[Fixture] = []
        for item in response:
            if not isinstance(item, Mapping):
                raise TypeError("API-Football fixture item must be an object")
            fixtures.append(self._adapter.adapt(item))
        return tuple(fixtures)


class DateShardDiscoveryError(RuntimeError):
    """One required calendar-date shard was unavailable or deferred."""
