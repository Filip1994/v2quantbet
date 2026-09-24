from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from h2h.domain.final_quote import FinalQuoteClaim, FinalQuoteStatus
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.odds import ApiBudgetExceededError
from h2h.persistence.postgres_runtime import OpportunityFixture, OpportunitySelection
from h2h.workers.opportunity import OpportunityWorker, _final_market
from h2h.workers.quote_refresh_schedule import StaleQuoteRetryPolicy


NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)
POLICY = StaleQuoteRetryPolicy(timedelta(minutes=2), timedelta(minutes=15), 5, timedelta(hours=1))


def market(odd: float, *, observed_at: datetime = NOW - timedelta(seconds=10)):
    return (
        CanonicalQuote(
            "api-football:1",
            8,
            "Bet365",
            Market.BTTS,
            Selection.YES,
            odd,
            observed_at,
            "api-football",
        ),
        CanonicalQuote(
            "api-football:1",
            8,
            "Bet365",
            Market.BTTS,
            Selection.NO,
            1.9,
            observed_at,
            "api-football",
        ),
    )


class Repository:
    def __init__(self):
        self.fixture = OpportunityFixture(
            "api-football:1",
            SimpleNamespace(fixture_id="api-football:1"),
            140,
            2026,
            NOW + timedelta(hours=2),
            NOW,
        )
        self.refresh_states = []

    def select_opportunity_fixtures(self, **_kwargs):
        return OpportunitySelection(1, 0, 0, 0, (self.fixture,))

    def latest_complete_market_states(self, *_args):
        return (SimpleNamespace(market="BTTS", observed_at=NOW, captured_at=NOW),)

    def record_quote_refresh_state(self, *_args, **kwargs):
        self.refresh_states.append(kwargs)
        return SimpleNamespace(stale_attempt_count=1, next_retry_at=NOW + timedelta(minutes=2))

    def latest_complete_snapshot_ids(self, *_args):
        return ("preliminary",)

    def snapshot_ids_for_market_observation(self, *_args):
        return (("NO", "final-no"), ("YES", "final-yes"))

    def clear_item_failure(self, *_args):
        return None

    def record_item_failures(self, *_args):
        return None


class Evaluator:
    def __init__(self, preliminary_odd=2.1, final_odd=2.0, final_edge=0.08, final_ev=0.12):
        self.preliminary_odd = preliminary_odd
        self.final_odd = final_odd
        self.final_edge = final_edge
        self.final_ev = final_ev

    def execute(self, _prediction_id, snapshot_id):
        final = snapshot_id == "final-yes"
        return SimpleNamespace(
            evaluation_id="evaluation-final" if final else "evaluation-preliminary",
            fixture_id="api-football:1",
            bookmaker_id=8,
            bookmaker_key="Bet365",
            market=Market.BTTS,
            selected_selection=Selection.YES,
            selected_odd=self.final_odd if final else self.preliminary_odd,
            edge=self.final_edge if final else 0.1,
            expected_value=self.final_ev if final else 0.15,
            model_probability=0.56,
            source="api-football",
        )


class Registration:
    def __init__(self, *, candidate=True, accept=True, prior_claim=None):
        self.candidate = candidate
        self.accept = accept
        self.prior_claim = prior_claim
        self.rejections = []
        self.completed = []
        self.executed = []

    def preliminary_rejection_codes(self, _evaluation_id):
        return () if self.candidate else ("EDGE_BELOW_MINIMUM",)

    def begin_final_quote_verification(self, evaluation_id):
        return self.prior_claim or FinalQuoteClaim(
            "verification-1", evaluation_id, FinalQuoteStatus.REQUESTED, True
        )

    def reject_final_quote_verification(self, verification_id, **kwargs):
        self.rejections.append((verification_id, kwargs))
        return FinalQuoteClaim(
            verification_id,
            "evaluation-preliminary",
            FinalQuoteStatus.REJECTED,
            False,
            reason_codes=kwargs["reason_codes"],
        )

    def complete_final_quote_verification(self, verification_id, evaluation_id, **kwargs):
        self.completed.append((verification_id, evaluation_id, kwargs))
        return FinalQuoteClaim(
            verification_id,
            "evaluation-preliminary",
            FinalQuoteStatus.READY,
            False,
            evaluation_id,
        )

    def execute(self, evaluation_id, request_id, **kwargs):
        self.executed.append((evaluation_id, request_id, kwargs))
        return SimpleNamespace(
            pick=SimpleNamespace(pick_id="pick-1") if self.accept else None,
            decision=SimpleNamespace(
                outcome=SimpleNamespace(value="APPROVED" if self.accept else "REJECTED"),
                reason_codes=() if self.accept else ("EDGE_BELOW_MINIMUM",),
            ),
        )

    @staticmethod
    def minimum_playable_odds(model_probability):
        return 1.05 / model_probability


class Source:
    def __init__(self, final):
        self.final = final
        self.calls = 0

    def fetch_quotes(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return market(2.1)
        if isinstance(self.final, BaseException):
            raise self.final
        return self.final


def run(final, *, registration=None, evaluator=None):
    repository = Repository()
    registration = registration or Registration()
    source = Source(final)
    worker = OpportunityWorker(
        repository,
        source,
        SimpleNamespace(ingest=lambda _quotes, **_kwargs: 0),
        SimpleNamespace(execute=lambda _fixture_id: SimpleNamespace(prediction_id="prediction")),
        evaluator or Evaluator(),
        registration,
        bookmaker_id=8,
        allowed_statuses=("NS",),
        ensure_model_available=lambda _fixture: None,
        should_stop=lambda: False,
        maximum_quote_age_seconds=300,
        minimum_time_to_kickoff_seconds=600,
        stale_retry_policy=POLICY,
        clock=lambda: NOW,
    )
    return worker.run_once(), source, registration, repository


def test_candidate_requires_second_provider_request_and_accepts_final_reprice() -> None:
    cycle, source, registration, _ = run(market(2.0))

    assert source.calls == 2
    assert cycle.registered_pick_ids == ("pick-1",)
    assert registration.executed[0][0] == "evaluation-final"
    assert registration.completed[0][2]["stale_quote"] is False


def test_final_price_movement_can_reject_edge_or_ev() -> None:
    registration = Registration(accept=False)
    cycle, source, _, _ = run(
        market(1.6),
        registration=registration,
        evaluator=Evaluator(final_odd=1.6, final_edge=-0.02, final_ev=-0.10),
    )

    assert source.calls == 2
    assert cycle.registered_pick_ids == ()
    assert cycle.rejected_picks == 1


def test_stale_observed_at_is_preserved_as_warning_and_can_accept() -> None:
    stale = NOW - timedelta(hours=3)
    cycle, _, registration, repository = run(market(2.0, observed_at=stale))

    assert cycle.registered_pick_ids == ("pick-1",)
    assert registration.completed[0][2]["stale_quote"] is True
    assert registration.completed[0][2]["quote_age_seconds"] == 3 * 3600
    assert repository.refresh_states[-1]["freshness_state"] == "STALE"


def test_incomplete_final_market_rejects_without_registration() -> None:
    cycle, _, registration, _ = run(market(2.0)[:1])

    assert cycle.registered_pick_ids == ()
    assert registration.executed == []
    assert registration.rejections[0][1]["reason_codes"] == ("FINAL_QUOTE_MARKET_INCOMPLETE",)


def test_final_market_never_combines_sources_or_bookmakers() -> None:
    evaluation = Evaluator().execute("prediction", "preliminary")
    yes, no = market(2.0)
    mismatched_source = CanonicalQuote(
        no.fixture_id,
        no.bookmaker_id,
        no.bookmaker_name,
        no.market,
        no.selection,
        no.odd,
        no.observed_at,
        "other-source",
    )
    mismatched_bookmaker = CanonicalQuote(
        no.fixture_id,
        9,
        "Other",
        no.market,
        no.selection,
        no.odd,
        no.observed_at,
        no.source,
    )

    assert _final_market((yes, mismatched_source), evaluation) is None
    assert _final_market((yes, mismatched_bookmaker), evaluation) is None


def test_budget_denial_rejects_and_never_accepts() -> None:
    cycle, _, registration, _ = run(ApiBudgetExceededError("daily budget exhausted"))

    assert cycle.registered_pick_ids == ()
    assert cycle.budget_exhausted is True
    assert registration.rejections[0][1]["budget_outcome"] == "DENIED"


def test_non_candidate_spends_no_final_refresh_and_concurrent_claim_is_suppressed() -> None:
    below = Registration(candidate=False)
    first, source, _, _ = run(market(2.0), registration=below)
    assert source.calls == 1
    assert first.decisions == 0

    in_flight = Registration(
        prior_claim=FinalQuoteClaim(
            "verification-1",
            "evaluation-preliminary",
            FinalQuoteStatus.REQUESTED,
            False,
        )
    )
    second, source, _, _ = run(market(2.0), registration=in_flight)
    assert source.calls == 1
    assert second.registered_pick_ids == ()
