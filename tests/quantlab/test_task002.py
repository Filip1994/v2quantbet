from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from h2h.odds.budget import ApiBudgetExceededError
from h2h.persistence.model_lifecycle import ActiveModelUnavailableError
from h2h.quantlab.entrypoint import _log_latest_goal_picks
from h2h.quantlab.goal_lab.shadow_engine import GoalLabShadowPickEngine
from h2h.quantlab.runtime import QuantLabRuntime


NOW = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)


def _fixture():
    return {
        "fixture_id": "api-football:9001",
        "provider_fixture_id": 9001,
        "league_id": 39,
        "season": 2026,
        "home_team_id": 1,
        "away_team_id": 2,
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "Premier League",
        "country": "England",
        "competition_type": "League",
        "kickoff_at": NOW + timedelta(hours=4),
        "provider_status": "NS",
    }


def _pair(bookmaker_id=8, bookmaker_name="Bet365", over=2.0, under=1.8):
    captured = NOW - timedelta(minutes=10)
    return {
        "bookmaker_id": bookmaker_id,
        "bookmaker_name": bookmaker_name,
        "provider_bet_id": 5,
        "provider_bet_name": "Goals Over/Under",
        "market_key": "OU_25",
        "line": 2.5,
        "captured_at": captured,
        "selections": {
            "OVER": {
                "market_observation_id": f"obs-{bookmaker_id}-over",
                "odds": over,
                "provider_updated_at": captured,
            },
            "UNDER": {
                "market_observation_id": f"obs-{bookmaker_id}-under",
                "odds": under,
                "provider_updated_at": captured,
            },
        },
    }


class Repo:
    def __init__(self, pairs=()):
        self.pairs = tuple(pairs)
        self.decisions = []
        self.shadows = []
        self._decision_ids = set()
        self._shadow_ids = set()

    def goal_market_pairs(self, fixture_id, *, decision_at):
        assert fixture_id == "api-football:9001"
        assert decision_at == NOW
        return self.pairs

    def save_goal_decision(self, item):
        self.decisions.append(item)
        if item.decision_id in self._decision_ids:
            return False
        self._decision_ids.add(item.decision_id)
        return True

    def save_goal_shadow_bet(self, item, *, stake_minor):
        self.shadows.append((item, stake_minor))
        key = item.decision_id
        if key in self._shadow_ids:
            return False
        self._shadow_ids.add(key)
        return True


class Model:
    def market_probabilities(self, home_team_id, away_team_id):
        assert (home_team_id, away_team_id) == (1, 2)
        return {
            "OVER_2_5": 0.60,
            "UNDER_2_5": 0.40,
            "BTTS_YES": 0.55,
        }


class Loader:
    def execute(self, scope):
        assert scope.league_id == 39
        assert scope.season == 2026
        return SimpleNamespace(model_version_id="dc-control-v1", model=Model())


def test_goal_engine_creates_only_best_price_shadow_pick_and_records_passes():
    repo = Repo(
        (
            _pair(bookmaker_id=8, bookmaker_name="Bet365", over=2.0, under=1.8),
            _pair(bookmaker_id=11, bookmaker_name="1xBet", over=1.95, under=1.9),
        )
    )
    engine = GoalLabShadowPickEngine(repo, Loader())

    result = engine.run_fixture(_fixture(), decision_at=NOW)

    assert result.decisions_inserted == 4
    assert result.picks_inserted == 1
    picks = [item for item in repo.decisions if item.decision == "PICK"]
    assert len(picks) == 1
    pick = picks[0]
    assert pick.bookmaker_name == "Bet365"
    assert pick.market_key == "OU_25"
    assert pick.selection == "OVER"
    assert pick.odds == 2.0
    assert pick.model_probability == 0.60
    assert pick.market_probability > 0.47
    assert pick.edge > 0.12
    assert pick.expected_value == pytest.approx(0.20)
    assert any(item.reason == "BETTER_PRICE_AVAILABLE" for item in repo.decisions)
    assert repo.shadows[0][1] == 10_000


def test_goal_engine_is_idempotent_for_same_model_and_quote_evidence():
    repo = Repo((_pair(),))
    engine = GoalLabShadowPickEngine(repo, Loader())

    first = engine.run_fixture(_fixture(), decision_at=NOW)
    second = engine.run_fixture(_fixture(), decision_at=NOW)

    assert first.decisions_inserted == 2
    assert first.picks_inserted == 1
    assert second.decisions_inserted == 0
    assert second.picks_inserted == 0


def test_goal_engine_records_no_active_model_pass_without_market_lookup():
    class MissingLoader:
        def execute(self, _scope):
            raise ActiveModelUnavailableError("missing")

    class NoMarketRepo(Repo):
        def goal_market_pairs(self, *_args, **_kwargs):
            raise AssertionError("market lookup must not occur without a model")

    repo = NoMarketRepo()
    result = GoalLabShadowPickEngine(repo, MissingLoader()).run_fixture(
        _fixture(), decision_at=NOW
    )

    assert result.decisions_inserted == 1
    assert result.picks_inserted == 0
    assert repo.decisions[0].decision == "PASS"
    assert repo.decisions[0].reason == "NO_ACTIVE_MODEL"
    assert repo.shadows == []


def test_goal_engine_requires_complete_two_sided_market():
    repo = Repo(())
    result = GoalLabShadowPickEngine(repo, Loader()).run_fixture(
        _fixture(), decision_at=NOW
    )

    assert result.decisions_inserted == 1
    assert repo.decisions[0].reason == "NO_COMPLETE_GOAL_MARKET"
    assert repo.shadows == []


def test_runtime_evaluates_goal_shadow_picks_after_api_budget_stops_collection():
    fixture = _fixture()

    class BudgetRepo:
        def fixture_discovery_due(self, *_args, **_kwargs):
            return True

        def upcoming_fixtures(self, **_kwargs):
            return (fixture,)

    class ExhaustedProvider:
        def fetch_fixtures_for_date(self, _fixture_date):
            raise ApiBudgetExceededError("exhausted")

    class GoalEngine:
        def __init__(self):
            self.calls = []

        def run_fixture(self, item, *, decision_at):
            self.calls.append((item["fixture_id"], decision_at))
            return SimpleNamespace(decisions_inserted=1, picks_inserted=1)

    goal_engine = GoalEngine()
    runtime = QuantLabRuntime(
        BudgetRepo(),
        ExhaustedProvider(),
        clock=lambda: NOW,
        goal_engine=goal_engine,
    )

    result = runtime.run_once()

    assert result["fixtures_discovered"] == 0
    assert result["market_fixtures"] == 0
    assert result["goal_decisions"] == 1
    assert result["goal_picks"] == 1
    assert goal_engine.calls == [("api-football:9001", NOW)]


def test_goal_pick_operational_snapshot_is_bounded_and_read_only():
    class SnapshotRepo:
        def __init__(self):
            self.calls = []

        def list_bets(self, lab, *, limit):
            self.calls.append((lab, limit))
            return ()

    repo = SnapshotRepo()
    _log_latest_goal_picks(repo, limit=7)

    assert repo.calls == [("GOAL", 7)]
