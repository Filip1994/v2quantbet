"""Production result acquisition, settlement reconciliation, and CLV finalization."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from h2h.domain.fixture_result import ApiFootballSettlementResultNormalizer
from h2h.odds.api_football_client import ApiFootballClient
from h2h.odds import ApiBudgetExceededError
from h2h.odds.http import TransportError
from h2h.persistence.postgres_result_settlement import PostgreSQLResultSettlementRepository
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository

LOGGER = logging.getLogger("quantbet.results")


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


class ApiFootballResultSource:
    def __init__(self, client: ApiFootballClient) -> None:
        if not isinstance(client, ApiFootballClient):
            raise TypeError("client must be an ApiFootballClient")
        self._client = client

    def fetch(self, contexts: tuple[tuple[str, int], ...]) -> dict[str, Mapping[str, Any]]:
        found: dict[str, Mapping[str, Any]] = {}
        for offset in range(0, len(contexts), 20):
            chunk = contexts[offset : offset + 20]
            payload = self._client.fetch_fixture_results(
                fixture_ids=tuple(provider_id for _, provider_id in chunk)
            )
            records = self._response(payload)
            expected = {provider_id: fixture_id for fixture_id, provider_id in chunk}
            for record in records:
                fixture = record.get("fixture")
                if not isinstance(fixture, Mapping):
                    raise TypeError("API-Football fixture result is missing fixture")
                provider_id = fixture.get("id")
                if isinstance(provider_id, bool) or not isinstance(provider_id, int):
                    raise TypeError("fixture.id must be an integer")
                fixture_id = expected.get(provider_id)
                if fixture_id is None:
                    raise ValueError("API-Football returned an unrequested fixture")
                if fixture_id in found:
                    raise ValueError("API-Football returned a duplicate fixture")
                found[fixture_id] = record
        return found

    @staticmethod
    def _response(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        if not isinstance(payload, Mapping):
            raise TypeError("API-Football response must be an object")
        errors = payload.get("errors")
        if errors not in ({}, []):
            raise RuntimeError(f"API-Football returned errors: {errors}")
        response = payload.get("response")
        if not isinstance(response, list):
            raise TypeError("API-Football response must be a list")
        results = payload.get("results")
        if isinstance(results, bool) or not isinstance(results, int) or results != len(response):
            raise ValueError("API-Football results count does not match response")
        paging = payload.get("paging")
        if not isinstance(paging, Mapping) or paging.get("current") != 1 or paging.get("total") != 1:
            raise ValueError("API-Football fixture result response is incomplete")
        if not all(isinstance(item, Mapping) for item in response):
            raise TypeError("API-Football fixture result items must be objects")
        return tuple(response)


@dataclass(frozen=True, slots=True)
class ResultCycle:
    initialized_fixture_ids: tuple[str, ...]
    claimed_fixture_ids: tuple[str, ...]
    persisted_result_count: int
    settled_pick_ids: tuple[str, ...]
    clv_finalized_pick_ids: tuple[str, ...]
    pending_work: bool = False


class ReconcileFixtureResults:
    def __init__(
        self,
        repository: PostgreSQLResultSettlementRepository,
        source: ApiFootballResultSource,
        *,
        research: PostgreSQLResearchSignalRepository | None = None,
        clock: Callable[[], datetime],
        on_item_failure: Callable[[str, BaseException, datetime], None] | None = None,
        on_item_success: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] = lambda: False,
        max_items: int = 2,
    ) -> None:
        self._repository = repository
        self._source = source
        self._research = research
        self._clock = clock
        self._normalizer = ApiFootballSettlementResultNormalizer()
        self._on_item_failure = on_item_failure or (lambda _item, _error, _at: None)
        self._on_item_success = on_item_success or (lambda _item: None)
        self._should_stop = should_stop
        if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items <= 0:
            raise ValueError("max_items must be a positive integer")
        self._max_items = max_items
        self._has_pending = False

    @property
    def has_pending(self) -> bool:
        return self._has_pending

    def execute(self) -> ResultCycle:
        now = _now(self._clock)
        initialized = self._repository.reconcile(reconciled_at=now)
        claimed = self._repository.claim_due(claimed_at=now, limit=self._max_items)
        contexts = self._repository.provider_contexts(claimed)
        records: dict[str, Mapping[str, Any]] = {}
        for context in contexts:
            if self._should_stop():
                break
            try:
                records.update(self._source.fetch((context,)))
            except ApiBudgetExceededError:
                raise
            except (TransportError, TypeError, ValueError, RuntimeError) as exc:
                self._on_item_failure(context[0], exc, now)
                continue
        settled: list[str] = []
        clv: list[str] = []
        for fixture_id, _provider_id in contexts:
            if self._should_stop():
                break
            payload = records.get(fixture_id)
            if payload is None:
                continue
            try:
                result = self._normalizer.normalize(payload, fixture_id=fixture_id, acquired_at=now)
            except (TypeError, ValueError) as exc:
                self._on_item_failure(fixture_id, exc, now)
                continue
            self._repository.persist_result(result, checked_at=now)
            self._on_item_success(fixture_id)
            stable = self._repository.stable_result(fixture_id, as_of=now)
            if stable is None:
                continue
            for pick_id in self._repository.unsettled_pick_ids(fixture_id):
                self._repository.settle_pick(pick_id, stable, settled_at=now)
                settled.append(pick_id)
            for pick_id in self._repository.pick_ids_for_fixture(fixture_id):
                outcome = self._repository.finalize_clv(pick_id, realized_at=now)
                if outcome.clv_fact_id is not None:
                    clv.append(pick_id)
            if self._research is not None:
                try:
                    self._research.finalize_fixture_result(
                        fixture_id, stable, finalized_at=now
                    )
                except Exception as exc:  # noqa: BLE001 - research must not block settlement
                    LOGGER.exception(
                        "research result finalization failed",
                        extra={
                            "fixture_id": fixture_id,
                            "error_class": type(exc).__name__,
                        },
                    )
        self._has_pending = self._repository.has_due_results(as_of=_now(self._clock))
        return ResultCycle(
            initialized,
            claimed,
            len(records),
            tuple(settled),
            tuple(clv),
            self._has_pending,
        )