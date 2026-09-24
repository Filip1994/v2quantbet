from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import ClassVar

from h2h.domain.final_quote import FinalQuoteClaim, FinalQuoteStatus
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.persistence.postgres_runtime import OpportunityFixture, OpportunitySelection
from h2h.workers.opportunity import OpportunityWorker
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy


NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)
POLICY = StaleQuoteRetryPolicy(timedelta(minutes=2), timedelta(minutes=15), 5, timedelta(hours=1))


def quotes(
    bookmaker_id: int,
    odd: float,
    *,
    complete: bool = True,
    observed_at: datetime = NOW - timedelta(seconds=5),
):
    name = {8: "Bet365", 11: "1xBet", 34: "Superbet"}[bookmaker_id]
    result = (
        CanonicalQuote(
            "api-football:1",
            bookmaker_id,
            name,
            Market.BTTS,
            Selection.YES,
            odd,
            observed_at,
            "api-football",
        ),
        CanonicalQuote(
            "api-football:1",
            bookmaker_id,
            name,
            Market.BTTS,
            Selection.NO,
            1.9,
            observed_at,
            "api-football",
        ),
    )
    return result if complete else result[:1]


def ou_quotes(
    bookmaker_id: int,
    *,
    observed_at: datetime = NOW - timedelta(seconds=5),
):
    name = {8: "Bet365", 11: "1xBet", 34: "Superbet"}[bookmaker_id]
    return (
        CanonicalQuote(
            "api-football:1",
            bookmaker_id,
            name,
            Market.OU_25,
            Selection.OVER,
            2.0,
            observed_at,
            "api-football",
        ),
        CanonicalQuote(
            "api-football:1",
            bookmaker_id,
            name,
            Market.OU_25,
            Selection.UNDER,
            1.9,
            observed_at,
            "api-football",
        ),
    )


class Repository:
    fixture = OpportunityFixture(
        "api-football:1",
        SimpleNamespace(fixture_id="api-football:1"),
        140,
        2026,
        NOW + timedelta(hours=2),
        NOW,
    )

    def select_opportunity_fixtures(self, **_kwargs):
        return OpportunitySelection(1, 0, 0, 0, (self.fixture,))

    def latest_complete_market_states(self, *_args):
        return (
            SimpleNamespace(
                market="BTTS",
                observed_at=NOW - timedelta(seconds=5),
                captured_at=NOW,
                source="api-football",
            ),
        )

    def record_quote_refresh_state(self, *_args, **_kwargs):
        return SimpleNamespace(next_retry_at=None)

    def latest_complete_snapshot_ids(self, _fixture_id, bookmaker_id):
        return (f"pre-{bookmaker_id}",)

    def snapshot_ids_for_market_observation(self, _fixture_id, bookmaker_id, *_args):
        return (("NO", f"final-no-{bookmaker_id}"), ("YES", f"final-yes-{bookmaker_id}"))

    def clear_item_failure(self, *_args):
        pass

    def record_item_failures(self, *_args):
        pass


class Evaluator:
    odds: ClassVar[dict[int, float]] = {8: 2.0, 11: 2.2, 34: 2.1}

    def execute(self, _prediction_id, snapshot_id):
        bookmaker_id = int(snapshot_id.rsplit("-", 1)[1])
        return SimpleNamespace(
            evaluation_id=f"evaluation:{snapshot_id}",
            fixture_id="api-football:1",
            bookmaker_id=bookmaker_id,
            bookmaker_key={8: "bet365", 11: "1xbet", 34: "superbet"}[bookmaker_id],
            market=Market.BTTS,
            selected_selection=Selection.YES,
            selected_odd=self.odds[bookmaker_id],
            edge=0.1,
            expected_value=0.15,
            model_probability=0.56,
            source="api-football",
        )


class Registration:
    def __init__(self):
        self.rejected = []
        self.executed = []

    def preliminary_rejection_codes(self, _evaluation_id):
        return ()

    def begin_final_quote_verification(self, evaluation_id):
        return FinalQuoteClaim(
            f"verification:{evaluation_id}", evaluation_id, FinalQuoteStatus.REQUESTED, True
        )

    def reject_final_quote_verification(self, verification_id, **kwargs):
        self.rejected.append((verification_id, kwargs["reason_codes"]))

    def complete_final_quote_verification(self, verification_id, evaluation_id, **_kwargs):
        return FinalQuoteClaim(
            verification_id, evaluation_id, FinalQuoteStatus.READY, False, evaluation_id
        )

    def execute(self, evaluation_id, *_args, **_kwargs):
        self.executed.append(evaluation_id)
        return SimpleNamespace(
            pick=SimpleNamespace(pick_id="pick-superbet") if evaluation_id.endswith("34") else None,
            decision=SimpleNamespace(outcome=SimpleNamespace(value="APPROVED"), reason_codes=()),
        )

    @staticmethod
    def minimum_playable_odds(model_probability):
        return 1.05 / model_probability


class StalePublishedRepository(Repository):
    def latest_complete_market_states(self, *_args):
        return (
            SimpleNamespace(
                market="BTTS",
                observed_at=NOW - timedelta(hours=3),
                captured_at=NOW,
                source="api-football",
            ),
        )


def test_multi_bookmaker_accepts_bounded_latest_published_snapshot() -> None:
    calls = []
    stale = NOW - timedelta(hours=3)

    def fetch_quotes(**kwargs):
        calls.append(kwargs["bookmaker_id"])
        if kwargs["bookmaker_id"] is None:
            return (
                quotes(8, 2.0, observed_at=stale)
                + quotes(11, 2.2, observed_at=stale)
                + quotes(34, 2.1, observed_at=stale)
            )
        if kwargs["bookmaker_id"] == 11:
            return quotes(11, 2.2, complete=False, observed_at=stale)
        return quotes(
            kwargs["bookmaker_id"],
            Evaluator.odds[kwargs["bookmaker_id"]],
            observed_at=stale,
        )

    registration = Registration()
    worker = OpportunityWorker(
        StalePublishedRepository(),
        SimpleNamespace(fetch_quotes=fetch_quotes),
        SimpleNamespace(ingest=lambda *_args, **_kwargs: 0),
        SimpleNamespace(execute=lambda _fixture_id: SimpleNamespace(prediction_id="prediction")),
        Evaluator(),
        registration,
        bookmaker_id=8,
        bookmaker_ids=(8, 11, 34),
        allowed_statuses=("NS",),
        ensure_model_available=lambda _fixture: None,
        should_stop=lambda: False,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=POLICY,
        provider_snapshot_max_age_seconds=14400,
        clock=lambda: NOW,
    )

    cycle = worker.run_once()

    assert calls == [None, 11, 34]
    assert cycle.registered_pick_ids == ("pick-superbet",)
    assert cycle.stale_market_count == 3
    assert all(
        "FINAL_QUOTE_STALE" not in reason_codes
        for _, reason_codes in registration.rejected
    )


class MixedFreshnessRepository(Repository):
    def latest_complete_market_states(self, *_args):
        return (
            SimpleNamespace(
                market="BTTS",
                observed_at=NOW - timedelta(hours=5),
                captured_at=NOW,
                source="api-football",
            ),
            SimpleNamespace(
                market="OU_25",
                observed_at=NOW - timedelta(seconds=5),
                captured_at=NOW,
                source="api-football",
            ),
        )

    def latest_complete_snapshot_ids(self, _fixture_id, bookmaker_id):
        return (
            f"pre-btts-{bookmaker_id}",
            f"pre-ou-{bookmaker_id}",
        )


class MixedEvaluator:
    def execute(self, _prediction_id, snapshot_id):
        bookmaker_id = int(snapshot_id.rsplit("-", 1)[1])
        is_btts = "btts" in snapshot_id
        return SimpleNamespace(
            evaluation_id=f"evaluation:{snapshot_id}",
            fixture_id="api-football:1",
            bookmaker_id=bookmaker_id,
            bookmaker_key={8: "bet365", 11: "1xbet", 34: "superbet"}[bookmaker_id],
            market=Market.BTTS if is_btts else Market.OU_25,
            selected_selection=Selection.YES if is_btts else Selection.OVER,
            selected_odd=2.0,
            edge=-0.1,
            expected_value=-0.1,
            model_probability=0.50,
            source="api-football",
        )


class RejectBeforeFinal(Registration):
    def preliminary_rejection_codes(self, _evaluation_id):
        return ("EDGE_BELOW_MINIMUM",)


def test_hard_stale_market_does_not_block_fresh_market_at_same_bookmaker() -> None:
    worker = OpportunityWorker(
        MixedFreshnessRepository(),
        SimpleNamespace(
            fetch_quotes=lambda **_kwargs: tuple(
                quote
                for bookmaker_id in (8, 11, 34)
                for quote in (
                    quotes(bookmaker_id, 2.0, observed_at=NOW - timedelta(hours=5))
                    + ou_quotes(bookmaker_id, observed_at=NOW - timedelta(seconds=5))
                )
            )
        ),
        SimpleNamespace(ingest=lambda *_args, **_kwargs: 0),
        SimpleNamespace(execute=lambda _fixture_id: SimpleNamespace(prediction_id="prediction")),
        MixedEvaluator(),
        RejectBeforeFinal(),
        bookmaker_id=8,
        bookmaker_ids=(8, 11, 34),
        allowed_statuses=("NS",),
        ensure_model_available=lambda _fixture: None,
        should_stop=lambda: False,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=POLICY,
        provider_snapshot_max_age_seconds=14400,
        clock=lambda: NOW,
    )

    cycle = worker.run_once()

    assert cycle.prediction_ids == ("prediction",)
    assert cycle.fresh_market_count == 3
    assert cycle.hard_stale_market_count == 3
    assert cycle.stale_market_count == 3
    assert len(cycle.evaluation_ids) == 3
    assert all("pre-ou-" in item for item in cycle.evaluation_ids)


def test_best_price_is_final_verified_and_incomplete_winner_falls_back() -> None:
    calls = []

    def fetch_quotes(**kwargs):
        calls.append(kwargs["bookmaker_id"])
        if kwargs["bookmaker_id"] is None:
            return quotes(8, 2.0) + quotes(11, 2.2) + quotes(34, 2.1)
        if kwargs["bookmaker_id"] == 11:
            return quotes(11, 2.2, complete=False)
        return quotes(kwargs["bookmaker_id"], Evaluator.odds[kwargs["bookmaker_id"]])

    registration = Registration()
    worker = OpportunityWorker(
        Repository(),
        SimpleNamespace(fetch_quotes=fetch_quotes),
        SimpleNamespace(ingest=lambda *_args, **_kwargs: 0),
        SimpleNamespace(execute=lambda _fixture_id: SimpleNamespace(prediction_id="prediction")),
        Evaluator(),
        registration,
        bookmaker_id=8,
        bookmaker_ids=(8, 11, 34),
        allowed_statuses=("NS",),
        ensure_model_available=lambda _fixture: None,
        should_stop=lambda: False,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=POLICY,
        clock=lambda: NOW,
    )

    cycle = worker.run_once()

    assert calls == [None, 11, 34]
    assert cycle.registered_pick_ids == ("pick-superbet",)
    assert cycle.fallback_attempts == 1
    assert cycle.bookmaker_wins == ((34, 1),)
    assert registration.rejected[0][1] == ("FINAL_QUOTE_MARKET_INCOMPLETE",)
