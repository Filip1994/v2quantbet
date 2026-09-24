"""Bounded, replay-safe production opportunity processing."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from time import monotonic

from h2h.domain.quote_normalizer import QuoteNormalizationError
from h2h.domain.best_price import rank_best_prices
from h2h.domain.bookmaker_policy import API_FOOTBALL_BOOKMAKERS
from h2h.domain.final_quote import FinalQuoteRejectionCode, FinalQuoteStatus
from h2h.domain.market_snapshot import MarketSnapshot
from h2h.odds import ApiBudgetExceededError
from h2h.odds.api_football_service import ApiFootballOddsService
from h2h.odds.http import TransportError
from h2h.persistence.model_lifecycle import ActiveModelUnavailableError
from h2h.persistence.postgres_runtime import (
    OpportunityCursor,
    OpportunityFixture,
    OpportunitySelection,
    PostgreSQLRuntimeRepository,
)
from h2h.quant import DixonColesFitError
from h2h.use_cases.production_prediction import ProduceFixturePrediction
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.use_cases.register_pick import RegisterEligiblePick
from h2h.use_cases.value_evaluation import EvaluatePersistedPredictionQuote
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy


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
    model_unavailable_scope_counts: tuple[tuple[int, int, int], ...] = ()
    model_deferred_fixture_ids: tuple[str, ...] = ()
    pending_work: bool = False
    budget_exhausted: bool = False
    fresh_market_count: int = 0
    stale_market_count: int = 0
    stale_retries_requested: int = 0
    stale_retries_scheduled: int = 0
    stale_retries_cleared: int = 0
    stale_retries_suppressed_by_budget: int = 0
    stale_retries_stopped: int = 0
    odds_fetches: int = 0
    compared_quotes: int = 0
    preliminary_refreshes: int = 0
    final_refreshes: int = 0
    fallback_attempts: int = 0
    no_valid_quote_count: int = 0
    bookmaker_wins: tuple[tuple[int, int], ...] = ()
    hard_stale_market_count: int = 0
    live_corroborations: int = 0
    live_proxy_rejections: int = 0


class OpportunityOddsUnavailableError(RuntimeError):
    """The provider returned no usable quotes for a due fixture."""


def _final_market(quotes: tuple[object, ...], evaluation: object) -> MarketSnapshot | None:
    """Select one newest exact complete market from only the final response."""
    groups: dict[tuple[object, ...], list[object]] = {}
    for quote in quotes:
        if (
            quote.fixture_id == evaluation.fixture_id
            and quote.bookmaker_id == evaluation.bookmaker_id
            and quote.market == evaluation.market
        ):
            key = (
                quote.fixture_id,
                quote.bookmaker_id,
                quote.market,
                quote.source,
                quote.bookmaker_name,
                quote.observed_at,
            )
            groups.setdefault(key, []).append(quote)
    complete: list[MarketSnapshot] = []
    for grouped in groups.values():
        try:
            complete.append(MarketSnapshot.from_quotes(grouped))
        except (TypeError, ValueError):
            continue
    if not complete:
        return None
    return max(complete, key=lambda market: (market.observed_at, market.quotes[0].source))


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
        bookmaker_ids: tuple[int, ...] | None = None,
        allowed_statuses: tuple[str, ...],
        ensure_model_available: Callable[[OpportunityFixture], None],
        should_stop: Callable[[], bool],
        model_scope_status: Callable[[OpportunityFixture], str | None] = lambda _fixture: "ACTIVE",
        max_items: int = 10,
        max_wall_seconds: float = 30.0,
        maximum_quote_age_seconds: int,
        minimum_time_to_kickoff_seconds: int,
        stale_retry_policy: StaleQuoteRetryPolicy,
        provider_snapshot_max_age_seconds: int = 14400,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_items <= 0 or max_wall_seconds <= 0:
            raise ValueError("opportunity budgets must be positive")
        if maximum_quote_age_seconds <= 0 or minimum_time_to_kickoff_seconds <= 0:
            raise ValueError("quote age and kickoff bounds must be positive")
        if provider_snapshot_max_age_seconds < maximum_quote_age_seconds:
            raise ValueError(
                "provider snapshot max age must be at least the strict quote age"
            )
        self._repository = repository
        self._source = source
        self._ingestion = ingestion
        self._predictor = predictor
        self._evaluator = evaluator
        self._register = register
        self._bookmaker_id = bookmaker_id
        self._bookmaker_ids = tuple(dict.fromkeys(bookmaker_ids or (bookmaker_id,)))
        if not self._bookmaker_ids or any(
            item not in API_FOOTBALL_BOOKMAKERS for item in self._bookmaker_ids
        ):
            raise ValueError("bookmaker_ids must use the approved API-Football allowlist")
        self._allowed_statuses = allowed_statuses
        self._ensure_model_available = ensure_model_available
        self._model_scope_status = model_scope_status
        self._should_stop = should_stop
        self._max_items = max_items
        self._max_wall_seconds = max_wall_seconds
        self._maximum_quote_age_seconds = maximum_quote_age_seconds
        self._minimum_time_to_kickoff_seconds = minimum_time_to_kickoff_seconds
        self._stale_retry_policy = stale_retry_policy
        self._provider_snapshot_max_age_seconds = provider_snapshot_max_age_seconds
        self._clock = clock
        self._monotonic = monotonic_clock
        self._cursor: OpportunityCursor | None = None
        self._has_pending = False

    @property
    def has_pending(self) -> bool:
        return self._has_pending

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC)

    def _flush_failures(self, pending: list[tuple[str, str, BaseException, datetime]]) -> None:
        if not pending:
            return
        batch = getattr(self._repository, "record_item_failures", None)
        if batch is not None:
            batch(pending)
        else:
            for worker, item_id, error, failed_at in pending:
                self._repository.record_item_failure(worker, item_id, error, failed_at=failed_at)
        pending.clear()

    def run_once(self) -> OpportunityCycle:
        started = self._monotonic()
        selection_time = self._now()
        prior_cursor = self._cursor
        priority_selector = getattr(self._repository, "select_due_stale_quote_retries", None)
        priority_selection = (
            priority_selector(
                bookmaker_id=self._bookmaker_id,
                allowed_statuses=self._allowed_statuses,
                now=selection_time,
                maximum_quote_age_seconds=self._maximum_quote_age_seconds,
                minimum_time_to_kickoff_seconds=self._minimum_time_to_kickoff_seconds,
                stale_retry_policy=self._stale_retry_policy,
                item_limit=1,
            )
            if priority_selector is not None
            else OpportunitySelection(0, 0, 0, 0, ())
        )
        normal_limit = self._max_items - len(priority_selection.due_fixtures)
        selection = (
            self._repository.select_opportunity_fixtures(
                bookmaker_id=self._bookmaker_id,
                allowed_statuses=self._allowed_statuses,
                now=selection_time,
                item_limit=normal_limit,
                after=prior_cursor,
                maximum_quote_age_seconds=self._maximum_quote_age_seconds,
                minimum_time_to_kickoff_seconds=self._minimum_time_to_kickoff_seconds,
                stale_retry_policy=self._stale_retry_policy,
            )
            if normal_limit > 0
            else OpportunitySelection(0, 0, 0, 0, (), prior_cursor, True)
        )
        due = tuple(
            {
                fixture.fixture_id: fixture
                for fixture in (priority_selection.due_fixtures + selection.due_fixtures)
            }.values()
        )[: self._max_items]
        processed: list[str] = []
        failed: list[str] = []
        model_unavailable: list[str] = []
        model_deferred: list[str] = []
        odds_unavailable: list[str] = []
        predictions: list[str] = []
        evaluations: list[str] = []
        picks: list[str] = []
        quotes_fetched = 0
        fresh_quotes = 0
        decisions = 0
        rejected_picks = 0
        model_scope_cache: dict[tuple[int, int], ActiveModelUnavailableError | None] = {}
        coverage_status_cache: dict[tuple[int, int], str | None] = {}
        failures_to_persist: list[tuple[str, str, BaseException, datetime]] = []
        interrupted = False
        budget_exhausted = False
        fresh_market_count = 0
        stale_market_count = 0
        stale_retries_requested = 0
        stale_retries_scheduled = 0
        stale_retries_cleared = 0
        stale_retries_suppressed_by_budget = 0
        odds_fetches = 0
        compared_quotes = 0
        preliminary_refreshes = 0
        final_refreshes = 0
        fallback_attempts = 0
        no_valid_quote_count = 0
        bookmaker_wins: dict[int, int] = {}
        hard_stale_market_count = 0
        live_corroborations = 0
        live_proxy_rejections = 0
        try:
            for fixture in due:
                if self._should_stop():
                    interrupted = True
                    break
                if self._monotonic() - started >= self._max_wall_seconds:
                    budget_exhausted = True
                    break
                item_now = self._now()
                if fixture.next_retry_at is not None and fixture.next_retry_at > item_now:
                    continue
                scope = (fixture.league_id, fixture.season)
                if scope not in coverage_status_cache:
                    coverage_status_cache[scope] = self._model_scope_status(fixture)
                if coverage_status_cache[scope] != "ACTIVE":
                    model_deferred.append(fixture.fixture_id)
                    continue
                unavailable = model_scope_cache.get(scope)
                if scope not in model_scope_cache:
                    try:
                        self._ensure_model_available(fixture)
                    except ActiveModelUnavailableError as exc:
                        unavailable = exc
                    model_scope_cache[scope] = unavailable
                if unavailable is not None:
                    failure_at = self._now()
                    failures_to_persist.append(
                        (WORKER_NAME, fixture.fixture_id, unavailable, failure_at)
                    )
                    failed.append(fixture.fixture_id)
                    model_unavailable.append(fixture.fixture_id)
                    continue
                try:
                    if fixture.stale_retry:
                        stale_retries_requested += 1
                    quotes = self._source.fetch_quotes(
                        fixture_identity=fixture.identity,
                        bookmaker_id=(
                            self._bookmaker_id if len(self._bookmaker_ids) == 1 else None
                        ),
                    )
                    preliminary_refreshes += 1
                except ApiBudgetExceededError:
                    if fixture.stale_retry:
                        stale_retries_suppressed_by_budget += 1
                        budget_exhausted = True
                        LOGGER.warning(
                            "stale quote retry suppressed by provider budget",
                            extra={
                                "worker": WORKER_NAME,
                                "fixture_id": fixture.fixture_id,
                                "stale_retry_attempt": fixture.stale_quote_attempt_count + 1,
                            },
                        )
                        break
                    raise
                except (TransportError, QuoteNormalizationError, TypeError, RuntimeError) as exc:
                    failures_to_persist.append((WORKER_NAME, fixture.fixture_id, exc, self._now()))
                    failed.append(fixture.fixture_id)
                    odds_unavailable.append(fixture.fixture_id)
                    LOGGER.warning(
                        "opportunity provider item failed",
                        extra={
                            "worker": WORKER_NAME,
                            "fixture_id": fixture.fixture_id,
                            "error_class": type(exc).__name__,
                        },
                    )
                    continue
                if not quotes:
                    error = OpportunityOddsUnavailableError("provider returned no usable quotes")
                    failures_to_persist.append(
                        (WORKER_NAME, fixture.fixture_id, error, self._now())
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
                odds_fetches += 1
                fresh_quotes += self._ingestion.ingest(quotes)
                attempted_at = self._now()
                states_by_bookmaker = {
                    approved_id: self._repository.latest_complete_market_states(
                        fixture.fixture_id, approved_id
                    )
                    for approved_id in self._bookmaker_ids
                }
                capture_tolerance = timedelta(seconds=60)
                returned_states_by_bookmaker = {
                    approved_id: tuple(
                        state
                        for state in states
                        if timedelta(0) <= attempted_at - state.captured_at <= capture_tolerance
                    )
                    for approved_id, states in states_by_bookmaker.items()
                }
                market_states = tuple(
                    state
                    for states in returned_states_by_bookmaker.values()
                    for state in states
                )
                if not market_states:
                    no_valid_quote_count += 1
                    for approved_id in self._bookmaker_ids:
                        self._repository.record_quote_refresh_state(
                            fixture.fixture_id,
                            approved_id,
                            freshness_state="NO_USABLE_QUOTE",
                            attempted_at=attempted_at,
                            latest_observed_at=None,
                            latest_captured_at=None,
                            stale_retry_policy=self._stale_retry_policy,
                        )
                    error = OpportunityOddsUnavailableError(
                        "provider returned no complete supported two-way market in this cycle"
                    )
                    failures_to_persist.append(
                        (WORKER_NAME, fixture.fixture_id, error, attempted_at)
                    )
                    failed.append(fixture.fixture_id)
                    odds_unavailable.append(fixture.fixture_id)
                    continue

                strict_age = timedelta(seconds=self._maximum_quote_age_seconds)
                provider_age = timedelta(seconds=self._provider_snapshot_max_age_seconds)
                usable_market_keys: set[tuple[int, str]] = set()
                strict_fresh_bookmaker_ids: set[int] = set()
                usable_bookmaker_ids: set[int] = set()
                for approved_id, states in returned_states_by_bookmaker.items():
                    if not states:
                        self._repository.record_quote_refresh_state(
                            fixture.fixture_id,
                            approved_id,
                            freshness_state="NO_USABLE_QUOTE",
                            attempted_at=attempted_at,
                            latest_observed_at=None,
                            latest_captured_at=None,
                            stale_retry_policy=self._stale_retry_policy,
                        )
                        continue

                    stale_for_book = []
                    for state in states:
                        age = attempted_at - state.observed_at
                        if age < timedelta(0) or age > provider_age:
                            hard_stale_market_count += 1
                            stale_market_count += 1
                            stale_for_book.append(state)
                            continue
                        usable_market_keys.add((approved_id, state.market))
                        usable_bookmaker_ids.add(approved_id)
                        if age <= strict_age:
                            fresh_market_count += 1
                            strict_fresh_bookmaker_ids.add(approved_id)
                        else:
                            stale_market_count += 1
                            stale_for_book.append(state)

                    if stale_for_book:
                        oldest = min(stale_for_book, key=lambda state: state.observed_at)
                        refresh_state = self._repository.record_quote_refresh_state(
                            fixture.fixture_id,
                            approved_id,
                            freshness_state="STALE",
                            attempted_at=attempted_at,
                            latest_observed_at=oldest.observed_at,
                            latest_captured_at=max(state.captured_at for state in states),
                            stale_retry_policy=self._stale_retry_policy,
                        )
                        if refresh_state.next_retry_at is not None:
                            stale_retries_scheduled += 1
                    else:
                        self._repository.record_quote_refresh_state(
                            fixture.fixture_id,
                            approved_id,
                            freshness_state="FRESH",
                            attempted_at=attempted_at,
                            latest_observed_at=min(state.observed_at for state in states),
                            latest_captured_at=max(state.captured_at for state in states),
                            stale_retry_policy=self._stale_retry_policy,
                        )

                if (
                    fixture.quote_freshness_state == "STALE"
                    and strict_fresh_bookmaker_ids
                ):
                    stale_retries_cleared += 1
                if not usable_market_keys:
                    no_valid_quote_count += 1
                    error = OpportunityOddsUnavailableError(
                        "no current provider-published market is within the bounded age policy"
                    )
                    failures_to_persist.append(
                        (WORKER_NAME, fixture.fixture_id, error, attempted_at)
                    )
                    failed.append(fixture.fixture_id)
                    odds_unavailable.append(fixture.fixture_id)
                    continue

                try:
                    prediction = self._predictor.execute(fixture.fixture_id)
                    predictions.append(prediction.prediction_id)
                    snapshot_ids = tuple(
                        snapshot_id
                        for approved_id in sorted(usable_bookmaker_ids)
                        for snapshot_id in self._repository.latest_complete_snapshot_ids(
                            fixture.fixture_id, approved_id
                        )
                    )
                    evaluated_snapshots = tuple(
                        self._evaluator.execute(prediction.prediction_id, snapshot_id)
                        for snapshot_id in snapshot_ids
                    )
                    preliminary_evaluations = tuple(
                        evaluation
                        for evaluation in evaluated_snapshots
                        if (
                            evaluation.bookmaker_id,
                            evaluation.market.value,
                        )
                        in usable_market_keys
                    )
                    evaluations.extend(
                        preliminary.evaluation_id for preliminary in preliminary_evaluations
                    )
                    if len(self._bookmaker_ids) == 1:
                        ordered_preliminaries = tuple(
                            sorted(
                                preliminary_evaluations,
                                key=lambda candidate: (
                                    -float(candidate.expected_value),
                                    -float(candidate.edge),
                                    -float(candidate.selected_odd),
                                    candidate.evaluation_id,
                                ),
                            )
                        )
                    else:
                        ranked_sets = rank_best_prices(preliminary_evaluations)
                        ordered_preliminaries = tuple(
                            candidate for group in ranked_sets for candidate in group.candidates
                        )
                    compared_quotes += len(ordered_preliminaries)
                    registered_selection_keys: set[tuple[object, object]] = set()
                    for preliminary in ordered_preliminaries:
                        selection_key = (
                            getattr(preliminary.market, "value", preliminary.market),
                            getattr(
                                preliminary.selected_selection,
                                "value",
                                preliminary.selected_selection,
                            ),
                        )
                        if selection_key in registered_selection_keys:
                            continue
                        preliminary_rejections = self._register.preliminary_rejection_codes(
                            preliminary.evaluation_id
                        )
                        if preliminary_rejections:
                            LOGGER.info(
                                "opportunity did not qualify for final quote refresh",
                                extra={
                                    "worker": WORKER_NAME,
                                    "fixture_id": fixture.fixture_id,
                                    "market": preliminary.market.value,
                                    "selection": preliminary.selected_selection.value,
                                    "preliminary_odds": preliminary.selected_odd,
                                    "preliminary_edge": preliminary.edge,
                                    "preliminary_ev": preliminary.expected_value,
                                    "rejection_reasons": preliminary_rejections,
                                    "final_quote_refresh_requested": False,
                                },
                            )
                            continue

                        claim = self._register.begin_final_quote_verification(
                            preliminary.evaluation_id
                        )
                        if claim.status is FinalQuoteStatus.REJECTED:
                            rejected_picks += 1
                            decisions += 1
                            fallback_attempts += 1
                            continue
                        if claim.status is FinalQuoteStatus.READY:
                            registration = self._register.execute(
                                claim.final_evaluation_id,
                                registration_request_id(preliminary.evaluation_id),
                                final_quote_verification_id=claim.verification_id,
                            )
                            decisions += 1
                            if registration.pick is not None:
                                picks.append(registration.pick.pick_id)
                                registered_selection_keys.add(selection_key)
                                bookmaker_wins[preliminary.bookmaker_id] = (
                                    bookmaker_wins.get(preliminary.bookmaker_id, 0) + 1
                                )
                                break
                            else:
                                rejected_picks += 1
                                fallback_attempts += 1
                            continue
                        if not claim.should_fetch:
                            LOGGER.info(
                                "duplicate final quote verification suppressed",
                                extra={
                                    "worker": WORKER_NAME,
                                    "fixture_id": fixture.fixture_id,
                                    "market": preliminary.market.value,
                                    "selection": preliminary.selected_selection.value,
                                    "verification_id": claim.verification_id,
                                },
                            )
                            continue

                        request_at = self._now()
                        LOGGER.info(
                            "mandatory final quote verification requested",
                            extra={
                                "worker": WORKER_NAME,
                                "fixture_id": fixture.fixture_id,
                                "market": preliminary.market.value,
                                "selection": preliminary.selected_selection.value,
                                "preliminary_odds": preliminary.selected_odd,
                                "preliminary_edge": preliminary.edge,
                                "preliminary_ev": preliminary.expected_value,
                                "final_refresh_request_timestamp": request_at,
                                "provider": "api-football",
                                "bookmaker": preliminary.bookmaker_key,
                                "api_budget_outcome": "PENDING",
                            },
                        )
                        try:
                            final_quotes = self._source.fetch_quotes(
                                fixture_identity=fixture.identity,
                                bookmaker_id=preliminary.bookmaker_id,
                                market=preliminary.market,
                            )
                            odds_fetches += 1
                            final_refreshes += 1
                        except ApiBudgetExceededError:
                            self._register.reject_final_quote_verification(
                                claim.verification_id,
                                reason_codes=(
                                    FinalQuoteRejectionCode.FINAL_QUOTE_REFRESH_BUDGET_UNAVAILABLE.value,
                                ),
                                budget_outcome="DENIED",
                            )
                            budget_exhausted = True
                            decisions += 1
                            rejected_picks += 1
                            LOGGER.warning(
                                "mandatory final quote verification rejected",
                                extra={
                                    "worker": WORKER_NAME,
                                    "fixture_id": fixture.fixture_id,
                                    "market": preliminary.market.value,
                                    "selection": preliminary.selected_selection.value,
                                    "final_decision": "REJECTED",
                                    "rejection_reasons": (
                                        FinalQuoteRejectionCode.FINAL_QUOTE_REFRESH_BUDGET_UNAVAILABLE.value,
                                    ),
                                    "api_budget_outcome": "DENIED",
                                },
                            )
                            break
                        except (
                            TransportError,
                            QuoteNormalizationError,
                            TypeError,
                            RuntimeError,
                        ) as exc:
                            self._register.reject_final_quote_verification(
                                claim.verification_id,
                                reason_codes=(
                                    FinalQuoteRejectionCode.FINAL_QUOTE_REFRESH_PROVIDER_ERROR.value,
                                ),
                            )
                            decisions += 1
                            rejected_picks += 1
                            fallback_attempts += 1
                            LOGGER.warning(
                                "mandatory final quote verification provider failure",
                                extra={
                                    "worker": WORKER_NAME,
                                    "fixture_id": fixture.fixture_id,
                                    "market": preliminary.market.value,
                                    "selection": preliminary.selected_selection.value,
                                    "error_class": type(exc).__name__,
                                    "final_decision": "REJECTED",
                                    "rejection_reasons": (
                                        FinalQuoteRejectionCode.FINAL_QUOTE_REFRESH_PROVIDER_ERROR.value,
                                    ),
                                    "api_budget_outcome": "ALLOWED",
                                },
                            )
                            continue

                        captured_at = self._now()
                        final_quotes = tuple(final_quotes)
                        quotes_fetched += len(final_quotes)
                        fresh_quotes += self._ingestion.ingest(
                            final_quotes, captured_at=captured_at
                        )
                        final_market = _final_market(final_quotes, preliminary)
                        if final_market is None:
                            self._register.reject_final_quote_verification(
                                claim.verification_id,
                                reason_codes=(
                                    FinalQuoteRejectionCode.FINAL_QUOTE_MARKET_INCOMPLETE.value,
                                ),
                                returned_captured_at=captured_at,
                            )
                            decisions += 1
                            rejected_picks += 1
                            fallback_attempts += 1
                            continue

                        quote_age = (captured_at - final_market.observed_at).total_seconds()
                        selected_quote = final_market.quote_for(preliminary.selected_selection)
                        if quote_age < 0:
                            self._register.reject_final_quote_verification(
                                claim.verification_id,
                                reason_codes=("QUOTE_NOT_YET_AVAILABLE",),
                                returned_source=selected_quote.source,
                                returned_observed_at=final_market.observed_at,
                                returned_captured_at=captured_at,
                            )
                            decisions += 1
                            rejected_picks += 1
                            fallback_attempts += 1
                            continue
                        stale_quote = quote_age > self._maximum_quote_age_seconds
                        if stale_quote:
                            self._repository.record_quote_refresh_state(
                                fixture.fixture_id,
                                preliminary.bookmaker_id,
                                freshness_state="STALE",
                                attempted_at=captured_at,
                                latest_observed_at=final_market.observed_at,
                                latest_captured_at=captured_at,
                                stale_retry_policy=self._stale_retry_policy,
                            )
                            LOGGER.warning(
                                "final quote verification returned stale provider observation",
                                extra={
                                    "worker": WORKER_NAME,
                                    "fixture_id": fixture.fixture_id,
                                    "market": preliminary.market.value,
                                    "selection": preliminary.selected_selection.value,
                                    "returned_observed_at": final_market.observed_at,
                                    "captured_at": captured_at,
                                    "quote_age_seconds": quote_age,
                                    "stale_quote": True,
                                    "warning_codes": ("STALE_QUOTE_WARNING",),
                                },
                            )
                            if len(self._bookmaker_ids) > 1:
                                self._register.reject_final_quote_verification(
                                    claim.verification_id,
                                    reason_codes=(FinalQuoteRejectionCode.FINAL_QUOTE_STALE.value,),
                                    returned_source=selected_quote.source,
                                    returned_observed_at=final_market.observed_at,
                                    returned_captured_at=captured_at,
                                    quote_age_seconds=quote_age,
                                )
                                decisions += 1
                                rejected_picks += 1
                                fallback_attempts += 1
                                continue

                        exact_snapshots = self._repository.snapshot_ids_for_market_observation(
                            fixture.fixture_id,
                            preliminary.bookmaker_id,
                            preliminary.market.value,
                            final_market.observed_at,
                            selected_quote.source,
                        )
                        snapshot_by_selection = dict(exact_snapshots)
                        selected_snapshot_id = snapshot_by_selection.get(
                            preliminary.selected_selection.value
                        )
                        if selected_snapshot_id is None or len(exact_snapshots) != 2:
                            self._register.reject_final_quote_verification(
                                claim.verification_id,
                                reason_codes=(
                                    FinalQuoteRejectionCode.FINAL_QUOTE_MARKET_INCOMPLETE.value,
                                ),
                                returned_source=selected_quote.source,
                                returned_observed_at=final_market.observed_at,
                                returned_captured_at=captured_at,
                                quote_age_seconds=quote_age,
                            )
                            decisions += 1
                            rejected_picks += 1
                            fallback_attempts += 1
                            continue

                        final_evaluation = self._evaluator.execute(
                            prediction.prediction_id, selected_snapshot_id
                        )
                        evaluations.append(final_evaluation.evaluation_id)
                        # Model lifecycle may change during the network request.
                        self._ensure_model_available(fixture)
                        final_preview = self._register.preliminary_rejection_codes(
                            final_evaluation.evaluation_id
                        )
                        if (
                            self._model_scope_status(fixture) != "ACTIVE"
                            or FinalQuoteRejectionCode.MODEL_INACTIVE_OR_STALE.value
                            in final_preview
                        ):
                            self._register.reject_final_quote_verification(
                                claim.verification_id,
                                reason_codes=(
                                    FinalQuoteRejectionCode.MODEL_INACTIVE_OR_STALE.value,
                                ),
                                returned_source=selected_quote.source,
                                returned_observed_at=final_market.observed_at,
                                returned_captured_at=captured_at,
                                quote_age_seconds=quote_age,
                            )
                            decisions += 1
                            rejected_picks += 1
                            fallback_attempts += 1
                            continue
                        ready = self._register.complete_final_quote_verification(
                            claim.verification_id,
                            final_evaluation.evaluation_id,
                            captured_at=captured_at,
                            quote_age_seconds=quote_age,
                            snapshot_ids=tuple(value for _, value in exact_snapshots),
                            stale_quote=stale_quote,
                            model_probability=final_evaluation.model_probability,
                        )
                        registration = self._register.execute(
                            final_evaluation.evaluation_id,
                            registration_request_id(preliminary.evaluation_id),
                            final_quote_verification_id=ready.verification_id,
                        )
                        decisions += 1
                        if registration.pick is not None:
                            picks.append(registration.pick.pick_id)
                            registered_selection_keys.add(selection_key)
                            bookmaker_wins[final_evaluation.bookmaker_id] = (
                                bookmaker_wins.get(final_evaluation.bookmaker_id, 0) + 1
                            )
                            break
                        else:
                            rejected_picks += 1
                            fallback_attempts += 1
                        LOGGER.info(
                            "mandatory final quote verification decided",
                            extra={
                                "worker": WORKER_NAME,
                                "fixture_id": fixture.fixture_id,
                                "market": final_evaluation.market.value,
                                "selection": final_evaluation.selected_selection.value,
                                "preliminary_odds": preliminary.selected_odd,
                                "preliminary_edge": preliminary.edge,
                                "preliminary_ev": preliminary.expected_value,
                                "provider": final_evaluation.source,
                                "bookmaker": final_evaluation.bookmaker_key,
                                "returned_observed_at": final_market.observed_at,
                                "captured_at": captured_at,
                                "quote_age_seconds": quote_age,
                                "stale_quote": stale_quote,
                                "warning_codes": (("STALE_QUOTE_WARNING",) if stale_quote else ()),
                                "final_odds": final_evaluation.selected_odd,
                                "minimum_playable_odds": (
                                    self._register.minimum_playable_odds(
                                        final_evaluation.model_probability
                                    )
                                ),
                                "final_edge": final_evaluation.edge,
                                "final_ev": final_evaluation.expected_value,
                                "final_decision": registration.decision.outcome.value,
                                "rejection_reasons": registration.decision.reason_codes,
                                "api_budget_outcome": "ALLOWED",
                            },
                        )
                    self._repository.clear_item_failure(WORKER_NAME, fixture.fixture_id)
                    processed.append(fixture.fixture_id)
                except (ActiveModelUnavailableError, DixonColesFitError) as exc:
                    failures_to_persist.append((WORKER_NAME, fixture.fixture_id, exc, self._now()))
                    failed.append(fixture.fixture_id)
                    if isinstance(exc, ActiveModelUnavailableError):
                        model_unavailable.append(fixture.fixture_id)
        finally:
            self._flush_failures(failures_to_persist)
        self._has_pending = bool(
            priority_selection.has_more or selection.has_more or interrupted or budget_exhausted
        )
        self._cursor = prior_cursor if (interrupted or budget_exhausted) else selection.continuation
        unavailable_scope_counts = tuple(
            (
                league_id,
                season,
                sum(
                    fixture.league_id == league_id and fixture.season == season
                    for fixture in due
                    if fixture.fixture_id in model_unavailable
                ),
            )
            for (league_id, season), error in model_scope_cache.items()
            if error is not None
        )
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
            unavailable_scope_counts,
            model_deferred_fixture_ids=tuple(model_deferred),
            pending_work=self._has_pending,
            budget_exhausted=budget_exhausted,
            fresh_market_count=fresh_market_count,
            stale_market_count=stale_market_count,
            stale_retries_requested=stale_retries_requested,
            stale_retries_scheduled=stale_retries_scheduled,
            stale_retries_cleared=stale_retries_cleared,
            stale_retries_suppressed_by_budget=stale_retries_suppressed_by_budget,
            stale_retries_stopped=selection.stale_retries_stopped,
            odds_fetches=odds_fetches,
            compared_quotes=compared_quotes,
            preliminary_refreshes=preliminary_refreshes,
            final_refreshes=final_refreshes,
            fallback_attempts=fallback_attempts,
            no_valid_quote_count=no_valid_quote_count,
            bookmaker_wins=tuple(sorted(bookmaker_wins.items())),
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
                "model_training_deferred": len(cycle.model_deferred_fixture_ids),
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
                "model_unavailable_scopes": len(cycle.model_unavailable_scope_counts),
                "model_unavailable_by_scope": {
                    f"api-football:{league_id}:{season}": count
                    for league_id, season, count in cycle.model_unavailable_scope_counts
                },
                "pending_work": cycle.pending_work,
                "budget_exhausted": cycle.budget_exhausted,
                "fresh_market_count": cycle.fresh_market_count,
                "stale_market_count": cycle.stale_market_count,
                "stale_retries_requested": cycle.stale_retries_requested,
                "stale_retries_scheduled": cycle.stale_retries_scheduled,
                "stale_retries_cleared": cycle.stale_retries_cleared,
                "stale_retries_suppressed_by_budget": (cycle.stale_retries_suppressed_by_budget),
                "stale_retries_stopped": cycle.stale_retries_stopped,
                "odds_fetches": cycle.odds_fetches,
                "compared_quotes": cycle.compared_quotes,
                "preliminary_refreshes": cycle.preliminary_refreshes,
                "final_refreshes": cycle.final_refreshes,
                "fallback_attempts": cycle.fallback_attempts,
                "no_valid_quote_count": cycle.no_valid_quote_count,
                "bookmaker_wins": dict(cycle.bookmaker_wins),
                "max_items": self._max_items,
                "duration_seconds": self._monotonic() - started,
            },
        )
        return cycle
