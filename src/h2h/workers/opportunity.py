"""Bounded, replay-safe production opportunity processing."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from h2h.config import PilotScope
from h2h.domain.fixture import Fixture
from h2h.domain.quote_normalizer import QuoteNormalizationError
from h2h.odds import ApiBudgetExceededError
from h2h.odds.api_football_service import ApiFootballOddsService
from h2h.odds.http import TransportError
from h2h.persistence.model_lifecycle import ActiveModelUnavailableError
from h2h.persistence.postgres_runtime import PostgreSQLRuntimeRepository
from h2h.use_cases.production_prediction import ProduceFixturePrediction
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.use_cases.register_pick import RegisterEligiblePick
from h2h.use_cases.value_evaluation import EvaluatePersistedPredictionQuote


LOGGER = logging.getLogger("quantbet.opportunity")
WORKER_NAME = "opportunity"


def registration_request_id(evaluation_id: str) -> str:
    return "production-registration-v1:" + sha256(evaluation_id.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OpportunityCycle:
    due_fixture_ids: tuple[str, ...]
    processed_fixture_ids: tuple[str, ...]
    failed_fixture_ids: tuple[str, ...]
    prediction_ids: tuple[str, ...]
    evaluation_ids: tuple[str, ...]
    registered_pick_ids: tuple[str, ...]


class PilotFixtureDiscovery:
    """Restrict already Phase-I-scoped discovery to the explicit production pilot."""

    def __init__(
        self,
        discovery: object,
        scopes: tuple[PilotScope, ...],
        provider_fixture_ids: frozenset[int],
    ) -> None:
        self._discovery = discovery
        self._scopes = {(scope.league_id, scope.season) for scope in scopes}
        self._provider_fixture_ids = provider_fixture_ids

    def discover(self, start_at: datetime, end_at: datetime) -> Sequence[Fixture]:
        fixtures = self._discovery.discover(start_at, end_at)  # type: ignore[attr-defined]
        return tuple(
            fixture
            for fixture in fixtures
            if (fixture.competition_id, fixture.season) in self._scopes
            and (
                not self._provider_fixture_ids
                or fixture.provider_fixture_id in self._provider_fixture_ids
            )
        )


class OpportunityWorker:
    def __init__(
        self,
        repository: PostgreSQLRuntimeRepository,
        source: ApiFootballOddsService,
        ingestion: QuoteHistoryIngestionService,
        predictor: ProduceFixturePrediction,
        evaluator: EvaluatePersistedPredictionQuote,
        register: RegisterEligiblePick,
        *,
        scopes: tuple[PilotScope, ...],
        bookmaker_id: int,
        provider_fixture_ids: frozenset[int],
        allowed_statuses: tuple[str, ...],
        usable_scopes: Callable[[], frozenset[PilotScope]],
        should_stop: Callable[[], bool],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._source = source
        self._ingestion = ingestion
        self._predictor = predictor
        self._evaluator = evaluator
        self._register = register
        self._scopes = scopes
        self._bookmaker_id = bookmaker_id
        self._provider_fixture_ids = provider_fixture_ids
        self._allowed_statuses = allowed_statuses
        self._usable_scopes = usable_scopes
        self._should_stop = should_stop
        self._clock = clock

    def run_once(self) -> OpportunityCycle:
        now = self._clock().astimezone(UTC)
        due = self._repository.due_opportunity_fixtures(
            scopes=self._scopes,
            bookmaker_id=self._bookmaker_id,
            provider_fixture_ids=self._provider_fixture_ids,
            allowed_statuses=self._allowed_statuses,
            now=now,
        )
        processed: list[str] = []
        failed: list[str] = []
        predictions: list[str] = []
        evaluations: list[str] = []
        picks: list[str] = []
        for fixture in due:
            if self._should_stop():
                break
            scope = PilotScope(fixture.league_id, fixture.season)
            if scope not in self._usable_scopes():
                continue
            if not self._repository.item_retry_due(WORKER_NAME, fixture.fixture_id, now=now):
                continue
            try:
                quotes = self._source.fetch_quotes(fixture_identity=fixture.identity)
            except ApiBudgetExceededError:
                raise
            except (TransportError, QuoteNormalizationError, TypeError, RuntimeError) as exc:
                self._repository.record_item_failure(
                    WORKER_NAME, fixture.fixture_id, exc, failed_at=now
                )
                failed.append(fixture.fixture_id)
                LOGGER.warning(
                    "opportunity provider item failed",
                    extra={"worker": WORKER_NAME, "fixture_id": fixture.fixture_id, "error_class": type(exc).__name__},
                )
                continue
            # Persistence conflicts and database integrity failures are deliberately
            # outside the provider-error boundary and must reach the orchestrator.
            self._ingestion.ingest(quotes)

            try:
                prediction = self._predictor.execute(fixture.fixture_id)
                predictions.append(prediction.prediction_id)
                snapshot_ids = self._repository.latest_complete_snapshot_ids(
                    fixture.fixture_id, self._bookmaker_id
                )
                for snapshot_id in snapshot_ids:
                    evaluation = self._evaluator.execute(prediction.prediction_id, snapshot_id)
                    evaluations.append(evaluation.evaluation_id)
                    registration = self._register.execute(
                        evaluation.evaluation_id,
                        registration_request_id(evaluation.evaluation_id),
                    )
                    if registration.pick is not None:
                        picks.append(registration.pick.pick_id)
                self._repository.clear_item_failure(WORKER_NAME, fixture.fixture_id)
                processed.append(fixture.fixture_id)
            except ActiveModelUnavailableError as exc:
                self._repository.record_item_failure(
                    WORKER_NAME, fixture.fixture_id, exc, failed_at=now
                )
                failed.append(fixture.fixture_id)
                continue
        return OpportunityCycle(
            tuple(item.fixture_id for item in due),
            tuple(processed),
            tuple(failed),
            tuple(predictions),
            tuple(evaluations),
            tuple(picks),
        )
