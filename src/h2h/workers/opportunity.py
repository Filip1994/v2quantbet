"""Bounded, replay-safe production opportunity processing."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from h2h.domain.quote_normalizer import QuoteNormalizationError
from h2h.odds import ApiBudgetExceededError
from h2h.odds.api_football_service import ApiFootballOddsService
from h2h.odds.http import TransportError
from h2h.persistence.model_lifecycle import ActiveModelUnavailableError
from h2h.persistence.postgres_runtime import OpportunityFixture, PostgreSQLRuntimeRepository
from h2h.quant import DixonColesFitError
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
    quotes_fetched: int = 0
    fresh_quotes: int = 0
    decisions: int = 0
    eligible_fixtures: int = 0
    phase_i_excluded: int = 0
    waiting_for_window: int = 0
    waiting_for_refresh: int = 0
    model_unavailable_fixture_ids: tuple[str, ...] = ()
    odds_unavailable_fixture_ids: tuple[str, ...] = ()
    rejected_picks: int = 0


class OpportunityOddsUnavailableError(RuntimeError):
    """The provider returned no usable quotes for a due fixture."""


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
        bookmaker_id: int,
        allowed_statuses: tuple[str, ...],
        ensure_model_available: Callable[[OpportunityFixture], None],
        should_stop: Callable[[], bool],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._source = source
        self._ingestion = ingestion
        self._predictor = predictor
        self._evaluator = evaluator
        self._register = register
        self._bookmaker_id = bookmaker_id
        self._allowed_statuses = allowed_statuses
        self._ensure_model_available = ensure_model_available
        self._should_stop = should_stop
        self._clock = clock

    def run_once(self) -> OpportunityCycle:
        now = self._clock().astimezone(UTC)
        selection = self._repository.select_opportunity_fixtures(
            bookmaker_id=self._bookmaker_id,
            allowed_statuses=self._allowed_statuses,
            now=now,
        )
        due = selection.due_fixtures
        processed: list[str] = []
        failed: list[str] = []
        model_unavailable: list[str] = []
        odds_unavailable: list[str] = []
        predictions: list[str] = []
        evaluations: list[str] = []
        picks: list[str] = []
        quotes_fetched = 0
        fresh_quotes = 0
        decisions = 0
        rejected_picks = 0
        for fixture in due:
            if self._should_stop():
                break
            if not self._repository.item_retry_due(WORKER_NAME, fixture.fixture_id, now=now):
                continue
            try:
                self._ensure_model_available(fixture)
            except ActiveModelUnavailableError as exc:
                self._repository.record_item_failure(
                    WORKER_NAME, fixture.fixture_id, exc, failed_at=now
                )
                failed.append(fixture.fixture_id)
                model_unavailable.append(fixture.fixture_id)
                LOGGER.warning(
                    "opportunity model unavailable",
                    extra={
                        "worker": WORKER_NAME,
                        "fixture_id": fixture.fixture_id,
                        "error_class": type(exc).__name__,
                    },
                )
                continue
            try:
                quotes = self._source.fetch_quotes(
                    fixture_identity=fixture.identity,
                    bookmaker_id=self._bookmaker_id,
                )
            except ApiBudgetExceededError:
                raise
            except (TransportError, QuoteNormalizationError, TypeError, RuntimeError) as exc:
                self._repository.record_item_failure(
                    WORKER_NAME, fixture.fixture_id, exc, failed_at=now
                )
                failed.append(fixture.fixture_id)
                odds_unavailable.append(fixture.fixture_id)
                LOGGER.warning(
                    "opportunity provider item failed",
                    extra={"worker": WORKER_NAME, "fixture_id": fixture.fixture_id, "error_class": type(exc).__name__},
                )
                continue
            if not quotes:
                error = OpportunityOddsUnavailableError("provider returned no usable quotes")
                self._repository.record_item_failure(
                    WORKER_NAME, fixture.fixture_id, error, failed_at=now
                )
                failed.append(fixture.fixture_id)
                odds_unavailable.append(fixture.fixture_id)
                LOGGER.info(
                    "opportunity odds unavailable",
                    extra={"worker": WORKER_NAME, "fixture_id": fixture.fixture_id},
                )
                continue
            # Persistence conflicts and database integrity failures are deliberately
            # outside the provider-error boundary and must reach the orchestrator.
            quotes_fetched += len(quotes)
            fresh_quotes += self._ingestion.ingest(quotes)

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
                    decisions += 1
                    if registration.pick is not None:
                        picks.append(registration.pick.pick_id)
                    else:
                        rejected_picks += 1
                self._repository.clear_item_failure(WORKER_NAME, fixture.fixture_id)
                processed.append(fixture.fixture_id)
            except (ActiveModelUnavailableError, DixonColesFitError) as exc:
                self._repository.record_item_failure(
                    WORKER_NAME, fixture.fixture_id, exc, failed_at=now
                )
                failed.append(fixture.fixture_id)
                if isinstance(exc, ActiveModelUnavailableError):
                    model_unavailable.append(fixture.fixture_id)
                continue
        cycle = OpportunityCycle(
            tuple(item.fixture_id for item in due),
            tuple(processed),
            tuple(failed),
            tuple(predictions),
            tuple(evaluations),
            tuple(picks),
            quotes_fetched,
            fresh_quotes,
            decisions,
            selection.eligible_fixture_count,
            selection.phase_i_excluded_count,
            selection.waiting_for_window_count,
            selection.waiting_for_refresh_count,
            tuple(model_unavailable),
            tuple(odds_unavailable),
            rejected_picks,
        )
        LOGGER.info(
            "opportunity cycle outcomes",
            extra={
                "worker": WORKER_NAME,
                "due_fixtures": len(cycle.due_fixture_ids),
                "eligible_fixtures": cycle.eligible_fixtures,
                "phase_i_excluded": cycle.phase_i_excluded,
                "waiting_for_window": cycle.waiting_for_window,
                "waiting_for_refresh": cycle.waiting_for_refresh,
                "model_unavailable": len(cycle.model_unavailable_fixture_ids),
                "odds_unavailable": len(cycle.odds_unavailable_fixture_ids),
                "processed_fixtures": len(cycle.processed_fixture_ids),
                "failed_fixtures": len(cycle.failed_fixture_ids),
                "quotes_fetched": cycle.quotes_fetched,
                "fresh_quotes": cycle.fresh_quotes,
                "predictions": len(cycle.prediction_ids),
                "evaluations": len(cycle.evaluation_ids),
                "decisions": cycle.decisions,
                "registered_picks": len(cycle.registered_pick_ids),
                "rejected_picks": cycle.rejected_picks,
            },
        )
        return cycle
