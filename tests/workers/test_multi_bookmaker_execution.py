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


def quotes(bookmaker_id: int, odd: float, *, complete: bool = True):
    name = {8: "Bet365", 11: "1xBet", 34: "Superbet"}[bookmaker_id]
    result = (
        CanonicalQuote(
            "api-football:1",
            bookmaker_id,
            name,
            Market.BTTS,
            Selection.YES,
            odd,
            NOW - timedelta(seconds=5),
            "api-football",
        ),
        CanonicalQuote(
            "api-football:1",
            bookmaker_id,
            name,
            Market.BTTS,
            Selection.NO,
            1.9,
            NOW - timedelta(seconds=5),
            "api-football",
        ),
    )
    return result if complete else result[:1]


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
        return (SimpleNamespace(observed_at=NOW, captured_at=NOW),)

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
