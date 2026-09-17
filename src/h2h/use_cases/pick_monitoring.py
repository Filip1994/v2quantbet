"""Bounded production operations for registered-pick odds monitoring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from h2h.domain.fixture_identity import ResolvedFixtureIdentity
from h2h.domain.odds import CanonicalQuote
from h2h.domain.pick_monitoring import (
    ClosingFinalization,
    MonitoringRecord,
    OddsLifecyclePolicy,
    PickOddsLifecycle,
)
from h2h.persistence.pick_monitoring import (
    PickClosingNotDueError,
    PickMonitoringRepository,
)
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.domain.quote_normalizer import QuoteNormalizationError
from h2h.odds import ApiBudgetExceededError
from h2h.odds.http import TransportError


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


class RegisteredPickQuoteSource(Protocol):
    def fetch_quotes(
        self, *, fixture_identity: ResolvedFixtureIdentity
    ) -> tuple[CanonicalQuote, ...]: ...


class StartRegisteredPickMonitoring:
    def __init__(
        self,
        repository: PickMonitoringRepository,
        policy: OddsLifecyclePolicy,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._clock = clock

    def execute(self, pick_id: str) -> MonitoringRecord:
        return self._repository.start(pick_id, self._policy, started_at=_now(self._clock))


@dataclass(frozen=True, slots=True)
class RefreshResult:
    claimed_pick_ids: tuple[str, ...]
    refreshed_fixture_ids: tuple[str, ...]
    persisted_snapshot_count: int


class RefreshRegisteredPickOdds:
    def __init__(
        self,
        repository: PickMonitoringRepository,
        source: RegisteredPickQuoteSource,
        ingestion: QuoteHistoryIngestionService,
        *,
        clock: Callable[[], datetime],
        claim_limit: int = 100,
        on_item_failure: Callable[[str, BaseException, datetime], None] | None = None,
        on_item_success: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> None:
        self._repository = repository
        self._source = source
        self._ingestion = ingestion
        self._clock = clock
        self._claim_limit = claim_limit
        self._on_item_failure = on_item_failure or (lambda _item, _error, _at: None)
        self._on_item_success = on_item_success or (lambda _item: None)
        self._should_stop = should_stop

    def execute(self) -> RefreshResult:
        claimed = self._repository.claim_due(
            claimed_at=_now(self._clock), limit=self._claim_limit
        )
        identities = self._repository.fixture_identities_for_picks(claimed)
        refreshed: list[str] = []
        count = 0
        for identity in identities:
            if self._should_stop():
                break
            try:
                quotes = self._source.fetch_quotes(fixture_identity=identity)
            except ApiBudgetExceededError:
                raise
            except (TransportError, QuoteNormalizationError, TypeError, RuntimeError) as exc:
                self._on_item_failure(identity.fixture_id, exc, _now(self._clock))
                continue
            count += self._ingestion.ingest(quotes)
            refreshed.append(identity.fixture_id)
            self._on_item_success(identity.fixture_id)
        return RefreshResult(claimed, tuple(refreshed), count)


class FinalizePickClosingOdds:
    def __init__(
        self,
        repository: PickMonitoringRepository,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._clock = clock

    def execute(self, pick_id: str) -> ClosingFinalization:
        return self._repository.finalize(pick_id, finalized_at=_now(self._clock))


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    started_pick_ids: tuple[str, ...]
    finalized_pick_ids: tuple[str, ...]


class ReconcileRegisteredPickMonitoring:
    def __init__(
        self,
        repository: PickMonitoringRepository,
        policy: OddsLifecyclePolicy,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._clock = clock

    def execute(self) -> ReconciliationResult:
        now = _now(self._clock)
        started: list[str] = []
        for pick_id in self._repository.unstarted_pick_ids():
            self._repository.start(pick_id, self._policy, started_at=now)
            started.append(pick_id)
        finalized: list[str] = []
        for pick_id in self._repository.monitored_pick_ids():
            try:
                self._repository.finalize(pick_id, finalized_at=now)
            except PickClosingNotDueError:
                continue
            finalized.append(pick_id)
        return ReconciliationResult(tuple(started), tuple(finalized))


class ReadPickOddsLifecycle:
    def __init__(
        self, repository: PickMonitoringRepository, *, clock: Callable[[], datetime]
    ) -> None:
        self._repository = repository
        self._clock = clock

    def execute(self, pick_id: str) -> PickOddsLifecycle:
        return self._repository.read_lifecycle(pick_id, as_of=_now(self._clock))
