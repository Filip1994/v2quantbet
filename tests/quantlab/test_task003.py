from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from h2h.odds.budget import ApiBudgetExceededError
from h2h.quantlab.card_lab.shadow_engine import CardLabShadowPickEngine
from h2h.quantlab.corner_lab.shadow_engine import CornerLabShadowPickEngine
from h2h.quantlab.count_shadow import poisson_over_probability
from h2h.quantlab.runtime import QuantLabRuntime


NOW = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)


def _fixture():
    return {
        "fixture_id": "api-football:9100",
        "provider_fixture_id": 9100,
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


def _count_rows(
    *,
    lab: str,
    market_name: str,
    line: float,
    over: float,
    under: float,
    bookmaker_id: int = 8,
    bookmaker_name: str = "Bet365",
    bet_id: int = 120,
):
    captured = NOW - timedelta(minutes=10)
    return (
        {
            "market_observation_id": f"{lab}-{bookmaker_id}-over",
            "bookmaker_id": bookmaker_id,
            "bookmaker_name": bookmaker_name,
            "provider_bet_id": bet_id,
            "provider_bet_name": market_name,
            "raw_selection": f"Over {line:g}",
            "parsed_line": line,
            "odds": over,
            "provider_updated_at": captured,
            "captured_at": captured,
        },
        {
            "market_observation_id": f"{lab}-{bookmaker_id}-under",
            "bookmaker_id": bookmaker_id,
            "bookmaker_name": bookmaker_name,
            "provider_bet_id": bet_id,
            "provider_bet_name": market_name,
            "raw_selection": f"Under {line:g}",
            "parsed_line": line,
            "odds": under,
            "provider_updated_at": captured,
            "captured_at": captured,
        },
    )


class Repo:
    def __init__(self, rows=()):
        self.rows = tuple(rows)
        self.decisions = []
        self.shadows = []
        self._decision_ids = set()
        self._shadow_keys = set()
        self.corner_history = {}
        self.card_feature = None

    def count_market_rows(self, fixture_id, *, lab, decision_at):
        assert fixture_id == "api-football:9100"
        assert decision_at == NOW
        return self.rows

    def save_count_decision(self, item):
        self.decisions.append(item)
        if item.decision_id in self._decision_ids:
            return False
        self._decision_ids.add(item.decision_id)
        return True

    def save_count_shadow_bet(self, item, *, stake_minor):
        self.shadows.append((item, stake_minor))
        key = (item.lab, item.fixture_id, item.market_key, item.selection, item.line)
        if key in self._shadow_keys:
            return False
        self._shadow_keys.add(key)
        return True

    def team_corner_history(self, team_id, *, before, limit):
        assert before == NOW
        assert limit == 10
        return tuple(self.corner_history.get(team_id, ()))

    def latest_card_feature(self, fixture_id, *, decision_at):
        assert fixture_id == "api-football:9100"
        assert decision_at == NOW
        return self.card_feature


def _history(corners_for, corners_against, *, was_home, count=5):
    return tuple(
        {
            "fixture_id": f"hist-{was_home}-{idx}",
            "kickoff_at": NOW - timedelta(days=idx + 1),
            "corners_for": corners_for,
            "corners_against": corners_against,
            "was_home": was_home,
        }
        for idx in range(count)
    )


def test_corner_engine_creates_value_pick_from_stored_team_corner_history():
    repo = Repo(
        _count_rows(
            lab="CORNER",
            market_name="Total Corners",
            line=9.5,
            over=2.10,
            under=1.75,
        )
    )
    repo.corner_history = {
        1: _history(6, 4, was_home=True),
        2: _history(4, 6, was_home=False),
    }

    result = CornerLabShadowPickEngine(repo).run_fixture(_fixture(), decision_at=NOW)

    assert result.decisions_inserted == 2
    assert result.picks_inserted == 1
    picks = [item for item in repo.decisions if item.decision == "PICK"]
    assert len(picks) == 1
    pick = picks[0]
    assert pick.lab == "CORNER"
    assert pick.selection == "OVER"
    assert pick.line == 9.5
    assert pick.model_probability > pick.market_probability
    assert pick.expected_value > 0.04
    assert repo.shadows[0][1] == 10_000


def test_corner_engine_passes_without_enough_history_before_market_lookup():
    class NoMarketRepo(Repo):
        def count_market_rows(self, *_args, **_kwargs):
            raise AssertionError("market lookup must not occur without model history")

    repo = NoMarketRepo()
    repo.corner_history = {
        1: _history(6, 4, was_home=True, count=4),
        2: _history(4, 6, was_home=False, count=5),
    }

    result = CornerLabShadowPickEngine(repo).run_fixture(_fixture(), decision_at=NOW)

    assert result.decisions_inserted == 1
    assert result.picks_inserted == 0
    assert repo.decisions[0].reason == "INSUFFICIENT_CORNER_HISTORY"


def test_corner_engine_rejects_team_corner_market_semantics():
    repo = Repo(
        _count_rows(
            lab="CORNER",
            market_name="Home Team Total Corners",
            line=5.5,
            over=2.0,
            under=1.8,
        )
    )
    repo.corner_history = {
        1: _history(6, 4, was_home=True),
        2: _history(4, 6, was_home=False),
    }

    CornerLabShadowPickEngine(repo).run_fixture(_fixture(), decision_at=NOW)

    assert len(repo.decisions) == 1
    assert repo.decisions[0].reason == "NO_CANONICAL_CORNER_MARKET"
    assert repo.shadows == []


def test_card_engine_uses_referee_rate_with_complete_context_gate():
    repo = Repo(
        _count_rows(
            lab="CARD",
            market_name="Total Cards",
            line=4.5,
            over=2.05,
            under=1.75,
        )
    )
    repo.card_feature = {
        "referee": "Ref A",
        "referee_card_rate": 5.0,
        "referee_sample_size": 12,
        "referee_foul_rate": 24.0,
        "referee_foul_sample_size": 12,
        "derby_rivalry_indicator": 1,
        "table_pressure": 0.7,
        "match_importance": 0.8,
        "feature_version": "CARDLAB_FEATURES_V1",
    }

    result = CardLabShadowPickEngine(repo).run_fixture(_fixture(), decision_at=NOW)

    assert result.decisions_inserted == 2
    assert result.picks_inserted == 1
    pick = next(item for item in repo.decisions if item.decision == "PICK")
    assert pick.lab == "CARD"
    assert pick.selection == "OVER"
    assert pick.model_version == "CARD_REFEREE_POISSON_V1"
    assert pick.details["context_role"] == "eligibility_and_audit_only"
    assert pick.details["match_importance"] == pytest.approx(0.8)


def test_card_engine_rejects_booking_points_market():
    repo = Repo(
        _count_rows(
            lab="CARD",
            market_name="Total Booking Points",
            line=44.5,
            over=2.0,
            under=1.8,
        )
    )
    repo.card_feature = {
        "referee": "Ref A",
        "referee_card_rate": 5.0,
        "referee_sample_size": 12,
        "referee_foul_rate": 24.0,
        "referee_foul_sample_size": 12,
        "derby_rivalry_indicator": 0,
        "table_pressure": 0.5,
        "match_importance": 0.5,
        "feature_version": "CARDLAB_FEATURES_V1",
    }

    CardLabShadowPickEngine(repo).run_fixture(_fixture(), decision_at=NOW)

    assert repo.decisions[0].reason == "NO_CANONICAL_CARD_MARKET"
    assert repo.shadows == []


def test_runtime_evaluates_corner_and_card_after_api_budget_stops_collection():
    fixture = _fixture()

    class BudgetRepo:
        def fixture_discovery_due(self, *_args, **_kwargs):
            return True

        def upcoming_fixtures(self, **_kwargs):
            return (fixture,)

    class ExhaustedProvider:
        def fetch_fixtures_for_date(self, _fixture_date):
            raise ApiBudgetExceededError("exhausted")

    class Engine:
        def __init__(self):
            self.calls = []

        def run_fixture(self, item, *, decision_at):
            self.calls.append((item["fixture_id"], decision_at))
            return SimpleNamespace(decisions_inserted=2, picks_inserted=1)

    corner = Engine()
    card = Engine()
    runtime = QuantLabRuntime(
        BudgetRepo(),
        ExhaustedProvider(),
        clock=lambda: NOW,
        corner_engine=corner,
        card_engine=card,
    )

    result = runtime.run_once()

    assert result["corner_decisions"] == 2
    assert result["corner_picks"] == 1
    assert result["card_decisions"] == 2
    assert result["card_picks"] == 1
    assert corner.calls == [("api-football:9100", NOW)]
    assert card.calls == [("api-football:9100", NOW)]


def test_count_poisson_supports_half_lines_and_rejects_push_lines():
    assert 0.0 < poisson_over_probability(10.0, 9.5) < 1.0
    with pytest.raises(ValueError, match="half-count"):
        poisson_over_probability(10.0, 10.0)


def test_corner_engine_is_idempotent_and_uses_best_qualifying_price():
    rows = (
        *_count_rows(
            lab="CORNER",
            market_name="Total Corners",
            line=9.5,
            over=2.10,
            under=1.75,
            bookmaker_id=8,
            bookmaker_name="Bet365",
            bet_id=120,
        ),
        *_count_rows(
            lab="CORNER",
            market_name="Total Corners",
            line=9.5,
            over=2.00,
            under=1.82,
            bookmaker_id=11,
            bookmaker_name="1xBet",
            bet_id=120,
        ),
    )
    repo = Repo(rows)
    repo.corner_history = {
        1: _history(6, 4, was_home=True),
        2: _history(4, 6, was_home=False),
    }
    engine = CornerLabShadowPickEngine(repo)

    first = engine.run_fixture(_fixture(), decision_at=NOW)
    second = engine.run_fixture(_fixture(), decision_at=NOW)

    assert first.picks_inserted == 1
    assert second.picks_inserted == 0
    pick = next(item for item in repo.decisions if item.decision == "PICK")
    assert pick.bookmaker_name == "Bet365"
    assert pick.odds == pytest.approx(2.10)
    assert any(item.reason == "BETTER_PRICE_AVAILABLE" for item in repo.decisions)
