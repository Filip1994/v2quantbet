from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from h2h.domain.fixture import Fixture
from h2h.domain.fixture_record import FixtureIdentityRecord, FixtureObservation, PersistedFixture
from h2h.domain.model_lifecycle import DixonColesModelScope
from h2h.domain.odds import CanonicalQuote, Market, Selection
from h2h.domain.prediction_record import PersistedFixturePrediction
from h2h.persistence.quote_history import InMemoryQuoteHistoryRepository, QuoteHistoryConflictError
from h2h.quant.dixon_coles import DixonColesModel
from h2h.use_cases.durable_fixture_discovery import DurableFixtureDiscovery
from h2h.use_cases.production_prediction import ProduceFixturePrediction
from h2h.use_cases.quote_history import QuoteHistoryIngestionService
from h2h.use_cases.value_evaluation import (
    EvaluatePersistedPredictionQuote,
    EvaluationFixtureMismatchError,
)


NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


def fixture(**changes):
    values = {
        "fixture_id": "api-football:123",
        "home_team": "Home",
        "away_team": "Away",
        "competition_id": 39,
        "competition_name": "Premier League",
        "country": "England",
        "kickoff_at": NOW + timedelta(days=1),
        "competition_type": "League",
        "season": 2026,
        "status": "NS",
        "provider": "api-football",
        "provider_fixture_id": "123",
        "provider_home_team_id": 10,
        "provider_away_team_id": 20,
    }
    values.update(changes)
    return Fixture(**values)


class MemoryFixtures:
    def __init__(self):
        self.items = {}

    def record_discovery(self, value, *, observed_at):
        existing = self.items.get(value.fixture_id)
        anchor = (
            value.provider,
            value.provider_fixture_id,
            value.competition_id,
            value.season,
            value.provider_home_team_id,
            value.provider_away_team_id,
        )
        if existing is not None:
            old = existing.identity
            if anchor != (
                old.provider,
                old.provider_fixture_id,
                old.league_id,
                old.season,
                old.provider_home_team_id,
                old.provider_away_team_id,
            ):
                raise ValueError("immutable fixture identity conflicts")
        identity = FixtureIdentityRecord(
            value.fixture_id,
            value.provider,
            value.provider_fixture_id,
            value.competition_id,
            value.season,
            value.provider_home_team_id,
            value.provider_away_team_id,
            existing.identity.created_at if existing else observed_at,
        )
        observation = FixtureObservation(
            f"fixture-observation-v1:{int(observed_at.timestamp()):064x}",
            value.fixture_id,
            value.home_team,
            value.away_team,
            value.competition_name,
            value.country,
            value.competition_type,
            value.kickoff_at,
            value.status,
            value.provider,
            observed_at,
            observed_at,
        )
        result = PersistedFixture(identity, observation)
        self.items[value.fixture_id] = result
        return result

    def get(self, fixture_id):
        return self.items.get(fixture_id)


class MemoryPredictions:
    def __init__(self):
        self.items = {}

    def add(self, value):
        old = self.items.get(value.prediction_id)
        if old is not None:
            return old
        self.items[value.prediction_id] = value
        return value

    def get(self, prediction_id):
        return self.items.get(prediction_id)


class MemoryEvaluations:
    def __init__(self):
        self.items = {}

    def add(self, value):
        return self.items.setdefault(value.evaluation_id, value)


def model():
    return DixonColesModel(
        team_ids=(10, 20),
        team_id_namespace="api-football",
        attacks=np.zeros(2),
        defenses=np.zeros(2),
        intercept=0.0,
        home_advantage=0.1,
        rho=0.0,
        xi=0.001,
        fitted_matches=80,
        objective=1.0,
    )


class ActiveLoader:
    def __init__(self, scope):
        self.scope = scope

    def execute_with_selection(self, requested):
        if requested != self.scope:
            raise RuntimeError("no active model for exact scope")
        loaded = SimpleNamespace(
            model_version_id="dcm-json-v1:" + "a" * 64,
            scope=self.scope,
            provenance=SimpleNamespace(scope=self.scope),
            model=model(),
        )
        return SimpleNamespace(
            loaded=loaded,
            scope=self.scope,
            model_version_id=loaded.model_version_id,
            generation=3,
            activated_at=NOW,
        )


def durable_fixture(repo):
    return repo.record_discovery(fixture(), observed_at=NOW)


def test_durable_discovery_appends_metadata_but_rejects_anchor_change() -> None:
    repo = MemoryFixtures()
    source = SimpleNamespace(discover=lambda start, end: (fixture(),))
    first = DurableFixtureDiscovery(source, repo, clock=lambda: NOW).discover(
        NOW, NOW + timedelta(days=2)
    )[0]
    changed = fixture(kickoff_at=fixture().kickoff_at + timedelta(hours=1), status="PST")
    source.discover = lambda start, end: (changed,)
    second = DurableFixtureDiscovery(
        source, repo, clock=lambda: NOW + timedelta(minutes=1)
    ).discover(NOW, NOW + timedelta(days=2))[0]
    assert first.identity == second.identity
    assert second.observation.provider_status == "PST"
    with pytest.raises(ValueError, match="immutable"):
        repo.record_discovery(
            fixture(provider_home_team_id=20, provider_away_team_id=10),
            observed_at=NOW + timedelta(minutes=2),
        )


def test_production_prediction_preserves_scope_generation_order_and_is_idempotent() -> None:
    fixtures, predictions = MemoryFixtures(), MemoryPredictions()
    durable_fixture(fixtures)
    scope = DixonColesModelScope("api-football", "api-football", 39, 2026)
    use_case = ProduceFixturePrediction(
        fixtures, ActiveLoader(scope), predictions, clock=lambda: NOW
    )
    first = use_case.execute("api-football:123")
    retry = use_case.execute("api-football:123")
    assert retry == first
    assert first.active_generation == 3
    assert (first.provider_home_team_id, first.provider_away_team_id) == (10, 20)
    assert first.model_version_id == "dcm-json-v1:" + "a" * 64


def test_no_model_scope_fallback_and_unknown_team_persist_nothing() -> None:
    fixtures, predictions = MemoryFixtures(), MemoryPredictions()
    durable_fixture(fixtures)
    wrong = DixonColesModelScope("api-football", "api-football", 40, 2026)
    with pytest.raises(RuntimeError, match="exact scope"):
        ProduceFixturePrediction(
            fixtures, ActiveLoader(wrong), predictions, clock=lambda: NOW
        ).execute("api-football:123")
    assert predictions.items == {}
    unknown_fixtures = MemoryFixtures()
    unknown_fixtures.record_discovery(
        fixture(provider_home_team_id=999), observed_at=NOW + timedelta(minutes=1)
    )
    with pytest.raises(RuntimeError):
        ProduceFixturePrediction(
            unknown_fixtures,
            ActiveLoader(DixonColesModelScope("api-football", "api-football", 39, 2026)),
            predictions,
            clock=lambda: NOW,
        ).execute("api-football:123")
    assert predictions.items == {}


def quote(selection, odd, fixture_id="api-football:123"):
    return CanonicalQuote(
        fixture_id=fixture_id,
        bookmaker_id=8,
        bookmaker_name="Bet365",
        market=Market.OU_25,
        selection=selection,
        odd=odd,
        observed_at=NOW,
        source="api-football",
    )


def stored_prediction(fixture_id="api-football:123"):
    return PersistedFixturePrediction(
        prediction_id="fixture-prediction-v1:" + "b" * 64,
        fixture_id=fixture_id,
        fixture_observation_id="fixture-observation-v1:" + "c" * 64,
        model_version_id="dcm-json-v1:" + "d" * 64,
        active_generation=1,
        model_activated_at=NOW,
        provider="api-football",
        team_id_namespace="api-football",
        league_id=39,
        season=2026,
        provider_home_team_id=10,
        provider_away_team_id=20,
        prediction_method_version="DIXON_COLES_MARKET_PROBABILITIES_V1",
        max_goals=10,
        over_2_5_probability=0.6,
        under_2_5_probability=0.4,
        btts_yes_probability=0.55,
        predicted_at=NOW,
        persisted_at=NOW,
    )


def test_value_evaluation_uses_exact_persisted_pair_and_devig() -> None:
    history = InMemoryQuoteHistoryRepository()
    QuoteHistoryIngestionService(history, capture_clock=lambda: NOW).ingest(
        (quote(Selection.OVER, 2.0), quote(Selection.UNDER, 1.8))
    )
    selected_id = history.snapshots_for_series(
        history.find_series(
            fixture_id="api-football:123", bookmaker_id=8, market="OU_25", selection="OVER"
        ).series_id
    )[0].snapshot_id
    predictions, evaluations = MemoryPredictions(), MemoryEvaluations()
    predictions.add(stored_prediction())
    use_case = EvaluatePersistedPredictionQuote(
        predictions, history, evaluations, clock=lambda: NOW
    )
    value = use_case.execute(stored_prediction().prediction_id, selected_id)
    assert value.model_probability == 0.6
    assert value.selected_raw_implied_probability == 0.5
    assert value.selected_devig_probability == pytest.approx(0.47368421052631576)
    assert value.edge == pytest.approx(0.12631578947368421)
    assert value.expected_value == pytest.approx(0.2)
    assert use_case.execute(stored_prediction().prediction_id, selected_id) == value


def test_incomplete_market_and_fixture_mismatch_fail_closed() -> None:
    history = InMemoryQuoteHistoryRepository()
    QuoteHistoryIngestionService(history, capture_clock=lambda: NOW).ingest(
        (quote(Selection.OVER, 2.0),)
    )
    snapshot_id = next(iter(history._snapshots))
    predictions, evaluations = MemoryPredictions(), MemoryEvaluations()
    predictions.add(stored_prediction())
    use_case = EvaluatePersistedPredictionQuote(
        predictions, history, evaluations, clock=lambda: NOW
    )
    with pytest.raises(QuoteHistoryConflictError, match="incomplete"):
        use_case.execute(stored_prediction().prediction_id, snapshot_id)
    assert evaluations.items == {}

    complete = InMemoryQuoteHistoryRepository()
    QuoteHistoryIngestionService(complete, capture_clock=lambda: NOW).ingest(
        (
            quote(Selection.OVER, 2.0, "api-football:999"),
            quote(Selection.UNDER, 1.8, "api-football:999"),
        )
    )
    snapshot_id = next(iter(complete._snapshots))
    with pytest.raises(EvaluationFixtureMismatchError):
        EvaluatePersistedPredictionQuote(
            predictions, complete, evaluations, clock=lambda: NOW
        ).execute(stored_prediction().prediction_id, snapshot_id)
    assert evaluations.items == {}
