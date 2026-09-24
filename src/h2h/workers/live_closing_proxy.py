"""Capture API-Football live odds immediately before kickoff as a market-close proxy."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from collections.abc import Callable

from h2h.odds import ApiBudgetExceededError
from h2h.odds.api_football_client import ApiFootballClient
from h2h.odds.api_football_live import parse_api_football_live_quotes
from h2h.odds.http import TransportError
from h2h.domain.quote_normalizer import QuoteNormalizationError
from h2h.persistence.postgres_live_closing_proxy import (
    PostgreSQLLiveClosingProxyRepository,
)


@dataclass(frozen=True, slots=True)
class LiveClosingProxyCycleResult:
    targeted_pick_ids: tuple[str, ...]
    requested_fixture_ids: tuple[int, ...]
    persisted_observations: int
    finalized_pick_ids: tuple[str, ...]


class LiveClosingProxyWorker:
    def __init__(
        self,
        repository: PostgreSQLLiveClosingProxyRepository,
        client: ApiFootballClient,
        *,
        clock: Callable[[], datetime],
        window_seconds: int = 900,
        max_age_seconds: int = 120,
        target_limit: int = 25,
        on_item_failure: Callable[[str, BaseException, datetime], None] | None = None,
        on_item_success: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> None:
        if window_seconds <= 0 or max_age_seconds <= 0 or target_limit <= 0:
            raise ValueError("live closing proxy bounds must be positive")
        self._repository = repository
        self._client = client
        self._clock = clock
        self._window_seconds = window_seconds
        self._max_age_seconds = max_age_seconds
        self._target_limit = target_limit
        self._on_item_failure = on_item_failure or (lambda _item, _error, _at: None)
        self._on_item_success = on_item_success or (lambda _item: None)
        self._should_stop = should_stop

    @staticmethod
    def _now(clock: Callable[[], datetime]) -> datetime:
        value = clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return timezone-aware datetime")
        return value.astimezone(UTC)

    def run_once(self) -> LiveClosingProxyCycleResult:
        now = self._now(self._clock)
        initial_finalizations = self._repository.finalize_due(
            as_of=now, max_age_seconds=self._max_age_seconds
        )
        targets = self._repository.capture_targets(
            as_of=now,
            window_seconds=self._window_seconds,
            limit=self._target_limit,
        )
        by_fixture: dict[int, list[object]] = defaultdict(list)
        for target in targets:
            by_fixture[target.provider_fixture_id].append(target)

        requested: list[int] = []
        persisted = 0
        for provider_fixture_id, fixture_targets in by_fixture.items():
            if self._should_stop():
                break
            item_id = fixture_targets[0].fixture_id
            try:
                payload = self._client.fetch_live_odds(fixture_id=provider_fixture_id)
                quotes = parse_api_football_live_quotes(payload, fixture_id=provider_fixture_id)
            except ApiBudgetExceededError:
                raise
            except (TransportError, QuoteNormalizationError, TypeError, RuntimeError) as exc:
                self._on_item_failure(item_id, exc, self._now(self._clock))
                continue
            requested.append(provider_fixture_id)
            by_identity = {(quote.market, quote.selection): quote for quote in quotes}
            captured_at = self._now(self._clock)
            for target in fixture_targets:
                quote = by_identity.get((target.market, target.selection))
                if quote is None:
                    continue
                if (
                    self._repository.persist_observation(
                        target, quote, captured_at=captured_at
                    )
                    is not None
                ):
                    persisted += 1
            self._on_item_success(item_id)

        after = self._now(self._clock)
        finalizations = self._repository.finalize_due(
            as_of=after, max_age_seconds=self._max_age_seconds
        )
        combined = initial_finalizations + finalizations
        return LiveClosingProxyCycleResult(
            tuple(target.pick_id for target in targets),
            tuple(requested),
            persisted,
            tuple(item.pick_id for item in combined),
        )
