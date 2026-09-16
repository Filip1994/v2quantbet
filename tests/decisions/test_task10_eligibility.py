from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from h2h.decisions.pick_eligibility import evaluate_persisted_eligibility
from h2h.domain.fixture_record import FixtureObservation
from h2h.domain.odds import Market, Selection
from h2h.domain.pick_decision import EligibilityRejectionCode
from h2h.domain.value_evaluation import PROPORTIONAL_TWO_WAY_V1, ValueEvaluation
from tests.domain.test_task10_policy import policy


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


def evaluation(**changes) -> ValueEvaluation:
    selected_odd, companion_odd, model_probability = 2.0, 1.8, 0.6
    selected_raw, companion_raw = 1 / selected_odd, 1 / companion_odd
    overround = selected_raw + companion_raw
    devig = selected_raw / overround
    values = {
        "evaluation_id": "value-evaluation-v1:" + "a" * 64,
        "fixture_id": "api-football:123",
        "prediction_id": "fixture-prediction-v1:" + "b" * 64,
        "model_version_id": "dcm-json-v1:" + "c" * 64,
        "selected_series_id": "series-over",
        "companion_series_id": "series-under",
        "selected_snapshot_id": "snapshot-over",
        "companion_snapshot_id": "snapshot-under",
        "bookmaker_id": 8,
        "bookmaker_key": "bet365",
        "market": Market.OU_25,
        "selected_selection": Selection.OVER,
        "companion_selection": Selection.UNDER,
        "quote_observed_at": NOW - timedelta(seconds=300),
        "source": "api-football",
        "selected_captured_at": NOW - timedelta(seconds=299),
        "companion_captured_at": NOW - timedelta(seconds=299),
        "selected_odd": selected_odd,
        "companion_odd": companion_odd,
        "selected_raw_implied_probability": selected_raw,
        "companion_raw_implied_probability": companion_raw,
        "overround": overround,
        "devig_method_version": PROPORTIONAL_TWO_WAY_V1,
        "selected_devig_probability": devig,
        "model_probability": model_probability,
        "edge": model_probability - devig,
        "expected_value": model_probability * selected_odd - 1,
        "evaluated_at": NOW - timedelta(seconds=250),
        "persisted_at": NOW - timedelta(seconds=250),
    }
    values.update(changes)
    return ValueEvaluation(**values)


def fixture(**changes) -> FixtureObservation:
    values = {
        "fixture_observation_id": "fixture-observation-v1:" + "d" * 64,
        "fixture_id": "api-football:123",
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "League",
        "country": "England",
        "competition_type": "League",
        "kickoff_at": NOW + timedelta(seconds=600),
        "provider_status": "NS",
        "source": "api-football",
        "observed_at": NOW - timedelta(minutes=1),
        "persisted_at": NOW - timedelta(minutes=1),
    }
    values.update(changes)
    return FixtureObservation(**values)


def test_all_threshold_equalities_pass() -> None:
    value = evaluation()
    exact = replace(
        policy(),
        minimum_edge=Decimal(str(value.edge)),
        minimum_expected_value=Decimal(str(value.expected_value)),
        minimum_odds=Decimal("2.0"),
        maximum_odds=Decimal("2.0"),
    )
    assert evaluate_persisted_eligibility(value, fixture(), exact, decided_at=NOW) == ()


def test_eligibility_collects_reasons_in_enum_order() -> None:
    value = evaluation(
        bookmaker_id=999,
        bookmaker_key="unknown",
        devig_method_version="OTHER",
        quote_observed_at=NOW + timedelta(seconds=1),
        selected_captured_at=NOW + timedelta(seconds=1),
        companion_captured_at=NOW + timedelta(seconds=1),
    )
    result = evaluate_persisted_eligibility(
        value,
        fixture(provider_status="PST"),
        replace(policy(), allowed_market_selections=((Market.BTTS, Selection.YES),)),
        decided_at=NOW,
    )
    assert result == tuple(code for code in EligibilityRejectionCode if code in set(result))
    assert EligibilityRejectionCode.MARKET_SELECTION_NOT_ALLOWED in result
    assert EligibilityRejectionCode.BOOKMAKER_NOT_ALLOWED in result
    assert EligibilityRejectionCode.DEVIG_METHOD_NOT_ALLOWED in result
    assert EligibilityRejectionCode.QUOTE_NOT_YET_AVAILABLE in result
    assert EligibilityRejectionCode.FIXTURE_STATUS_NOT_ALLOWED in result


def test_stale_future_and_post_kickoff_boundaries() -> None:
    stale = evaluation(
        quote_observed_at=NOW - timedelta(seconds=301),
        selected_captured_at=NOW - timedelta(seconds=300),
        companion_captured_at=NOW - timedelta(seconds=300),
    )
    assert EligibilityRejectionCode.QUOTE_TOO_OLD in evaluate_persisted_eligibility(
        stale, fixture(), policy(), decided_at=NOW
    )
    post_quote = evaluation(quote_observed_at=NOW - timedelta(seconds=300))
    past_fixture = fixture(kickoff_at=NOW - timedelta(seconds=301))
    result = evaluate_persisted_eligibility(post_quote, past_fixture, policy(), decided_at=NOW)
    assert EligibilityRejectionCode.QUOTE_NOT_PREMATCH in result
    assert EligibilityRejectionCode.REGISTRATION_NOT_PREMATCH in result


def test_kickoff_buffer_one_second_short_rejects() -> None:
    result = evaluate_persisted_eligibility(
        evaluation(), fixture(kickoff_at=NOW + timedelta(seconds=599)), policy(), decided_at=NOW
    )
    assert result == (EligibilityRejectionCode.REGISTRATION_TOO_CLOSE_TO_KICKOFF,)


def test_edge_ev_and_odds_failures_are_explicit() -> None:
    result = evaluate_persisted_eligibility(
        evaluation(),
        fixture(),
        replace(
            policy(),
            minimum_edge=Decimal("0.2"),
            minimum_expected_value=Decimal("0.3"),
            minimum_odds=Decimal("2.1"),
        ),
        decided_at=NOW,
    )
    assert result == (
        EligibilityRejectionCode.EDGE_BELOW_MINIMUM,
        EligibilityRejectionCode.EXPECTED_VALUE_BELOW_MINIMUM,
        EligibilityRejectionCode.ODDS_BELOW_MINIMUM,
    )
