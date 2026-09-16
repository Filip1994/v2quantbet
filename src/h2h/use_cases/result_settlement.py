"""Production result acquisition, settlement reconciliation, and CLV finalization."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from h2h.domain.fixture_result import ApiFootballSettlementResultNormalizer
from h2h.odds.api_football_client import ApiFootballClient
from h2h.persistence.postgres_result_settlement import PostgreSQLResultSettlementRepository


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


class ReconcileFixtureResults:
    def __init__(
        self,
        repository: PostgreSQLResultSettlementRepository,
        source: ApiFootballResultSource,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._source = source
        self._clock = clock
        self._normalizer = ApiFootballSettlementResultNormalizer()

    def execute(self) -> ResultCycle:
        now = _now(self._clock)
        initialized = self._repository.reconcile(reconciled_at=now)
        claimed = self._repository.claim_due(claimed_at=now)
        contexts = self._repository.provider_contexts(claimed)
        records = self._source.fetch(contexts) if contexts else {}
        settled: list[str] = []
        clv: list[str] = []
        for fixture_id, _provider_id in contexts:
            payload = records.get(fixture_id)
            if payload is None:
                continue
            result = self._normalizer.normalize(payload, fixture_id=fixture_id, acquired_at=now)
            self._repository.persist_result(result, checked_at=now)
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
        return ResultCycle(initialized, claimed, len(records), tuple(settled), tuple(clv))
