"""Bounded pre-kickoff close refreshes for exposure-blocked research signals."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from h2h.domain.quote_normalizer import QuoteNormalizationError
from h2h.odds import ApiBudgetExceededError
from h2h.odds.http import TransportError
from h2h.persistence.postgres_research_signals import (
    PostgreSQLResearchSignalRepository,
)
from h2h.use_cases.pick_monitoring import RegisteredPickQuoteSource
from h2h.use_cases.quote_history import QuoteHistoryIngestionService


LOGGER = logging.getLogger("quantbet.research_closing")
RESEARCH_CLOSE_REFRESH_INTERVAL_SECONDS = 300
RESEARCH_CLOSE_MAX_ITEMS = 5


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ResearchClosingCycle:
    claimed_target_count: int
    refreshed_fixture_count: int
    persisted_snapshot_count: int
    failed_target_count: int


class ResearchClosingWorker:
    """Refresh blocked-signal books only inside the bounded closing window."""

    def __init__(
        self,
        repository: PostgreSQLResearchSignalRepository,
        source: RegisteredPickQuoteSource,
        ingestion: QuoteHistoryIngestionService,
        *,
        clock: Callable[[], datetime],
        window_seconds: int,
        allowed_statuses: tuple[str, ...],
        refresh_interval_seconds: int = RESEARCH_CLOSE_REFRESH_INTERVAL_SECONDS,
        max_items: int = RESEARCH_CLOSE_MAX_ITEMS,
        on_item_failure: Callable[[str, BaseException, datetime], None] | None = None,
        on_item_success: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> None:
        if isinstance(window_seconds, bool) or not isinstance(window_seconds, int) or window_seconds <= 0:
            raise ValueError("window_seconds must be a positive integer")
        if (
            isinstance(refresh_interval_seconds, bool)
            or not isinstance(refresh_interval_seconds, int)
            or refresh_interval_seconds <= 0
        ):
            raise ValueError("refresh_interval_seconds must be a positive integer")
        if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items <= 0:
            raise ValueError("max_items must be a positive integer")
        self._repository = repository
        self._source = source
        self._ingestion = ingestion
        self._clock = clock
        self._window_seconds = window_seconds
        self._allowed_statuses = allowed_statuses
        self._refresh_interval_seconds = refresh_interval_seconds
        self._max_items = max_items
        self._on_item_failure = on_item_failure or (lambda _item, _error, _at: None)
        self._on_item_success = on_item_success or (lambda _item: None)
        self._should_stop = should_stop

    def run_once(self) -> ResearchClosingCycle:
        started = _now(self._clock)
        targets = self._repository.claim_due_close_targets(
            as_of=started,
            window_seconds=self._window_seconds,
            refresh_interval_seconds=self._refresh_interval_seconds,
            allowed_statuses=self._allowed_statuses,
            limit=self._max_items,
        )
        refreshed: set[str] = set()
        persisted = 0
        failures = 0
        for target in targets:
            if self._should_stop():
                break
            item_id = (
                f"{target.fixture_identity.fixture_id}:"
                f"{target.bookmaker_id}"
            )
            try:
                quotes = self._source.fetch_quotes(
                    fixture_identity=target.fixture_identity,
                    bookmaker_id=target.bookmaker_id,
                )
                count = self._ingestion.ingest(quotes)
                persisted += count
                refreshed.add(target.fixture_identity.fixture_id)
                self._repository.finish_close_refresh(
                    target,
                    outcome="SUCCESS" if quotes else "NO_QUOTES",
                    persisted_snapshot_count=count,
                    completed_at=_now(self._clock),
                )
                self._on_item_success(item_id)
            except ApiBudgetExceededError:
                raise
            except (TransportError, QuoteNormalizationError, TypeError, RuntimeError) as exc:
                failures += 1
                completed = _now(self._clock)
                self._repository.finish_close_refresh(
                    target,
                    outcome="ERROR",
                    persisted_snapshot_count=0,
                    completed_at=completed,
                    error_class=type(exc).__name__,
                )
                self._on_item_failure(item_id, exc, completed)
        result = ResearchClosingCycle(
            len(targets), len(refreshed), persisted, failures
        )
        LOGGER.info(
            "research closing cycle outcomes",
            extra={
                "worker": "research_closing",
                "research_close_claimed_target_count": result.claimed_target_count,
                "research_close_refreshed_fixture_count": result.refreshed_fixture_count,
                "research_close_persisted_snapshot_count": result.persisted_snapshot_count,
                "research_close_failed_target_count": result.failed_target_count,
            },
        )
        return result
