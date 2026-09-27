from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from h2h.quantlab.card_lab.shadow_engine import CardLabShadowPickEngine
from h2h.quantlab.corner_lab.shadow_engine import CornerLabShadowPickEngine


NOW = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)


def fixture() -> dict[str, object]:
    return {
        "fixture_id": "api-football:3001",
        "provider_fixture_id": 3001,
        "country": "England",
        "competition_name": "Premier League",
        "competition_type": "League",
        "home_team_id": 1,
        "away_team_id": 2,
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "kickoff_at": NOW + timedelta(hours=3),
    }


def market_pair(
    bookmaker_id: int,
    bookmaker_name: str,
    *,
    bet_id: int,
    bet_name: str,
    line: float,
    over: float,
    under: float,
) -> dict[str, object]:
    captured = NOW - timedelta(hours=1)
    prefix = f"{bookmaker_id}:{bet_id}:{line}"
    return {
        "bookmaker_id": bookmaker_id,
        "bookmaker_name": bookmaker_name,
        "provider_bet_id": bet_id,
        "provider_bet_name": bet_name,
        "line": line,
        "captured_at": captured,
        "selections": {
            "OVER": {
                "market_observation_id": f"obs:{prefix}:over",
                "odds": over,
            },
            "UNDER": {
                "market_observation_id": f"obs:{prefix}:under",
                "odds": under,
            },
        },
    }


class Repo:
    def __init__(self, *, pairs=(), card_feature=None):
        self.pairs = tuple(pairs)
        self.card_feature = card_feature
        self.decisions = []
        self.shadows = []
        self._decision_ids = set()
        self._shadow_keys = set()
        self.market_calls = []

    def total_market_pairs(self, fixture_id, *, lab_owner, decision_at):
        self.market_calls.append((fixture_id, lab_owner, decision_at))
        return self.pairs

    def latest_card_feature_snapshot(self, fixture_id, *, decision_at):
        return self.card_feature

    def save_context_market_decision(self, item):
        self.decisions.append(item)
        if item.decision_id in self._decision_ids:
            return False
        self._decision_ids.add(item.decision_id)
        return True

    def save_context_shadow_bet(self, item, *, stake_minor):
        key = (item.lab, item.fixture_id, item.market_key, item.line)
        self.shadows.append((item, stake_minor))
        if key in self._shadow_keys:
            return False
        self._shadow_keys.add(key)
        return True


class _CornerEstimate:
    expected_total_corners = 11.7
    model = SimpleNamespace(
        model_version="CORNER_PRESSURE_POISSON_V1:" + "a" * 64,
        feature_version="CORNER_PRESSURE_FEATURES_V1",
        training_sample_size=250,
        history_match_count=400,
    )
    snapshot = SimpleNamespace(home_history_size=12, away_history_size=10)

    def probability(self, selection, line):
        assert line == 10.5
        return 0.62 if selection == "OVER" else 0.38


class _CornerModel:
    def estimate(self, fixture, *, decision_at):
        assert fixture["home_team_id"] == 1
        assert fixture["away_team_id"] == 2
        assert decision_at == NOW
        return SimpleNamespace(
            estimate=_CornerEstimate(),
            reason="MODEL_READY",
            details={"training_sample_size": 250},
        )


def _corner_engine(repo):
    engine = CornerLabShadowPickEngine(repo)
    engine._model = _CornerModel()
    return engine


def test_corner_engine_uses_structural_model_and_needs_only_one_bookmaker():
    repo = Repo(
        pairs=(
            market_pair(
                8,
                "Bet365",
                bet_id=100,
                bet_name="Total Corners",
                line=10.5,
                over=2.20,
                under=1.65,
            ),
        )
    )

    result = _corner_engine(repo).run_fixture(fixture(), decision_at=NOW)

    assert result.decisions_inserted == 2
    assert result.picks_inserted == 1
    pick = next(item for item in repo.decisions if item.decision == "PICK")
    assert pick.lab == "CORNER"
    assert pick.market_key == "TOTAL_CORNERS"
    assert pick.selection == "OVER"
    assert pick.bookmaker_id == 8
    assert pick.reference_bookmaker_id is None
    assert pick.model_name == "Corner pressure Poisson GLM"
    assert pick.model_probability == 0.62
    assert pick.details["expected_total_corners"] == 11.7
    assert pick.details["cross_book_reference_used"] is False
    assert pick.edge > 0.03
    assert pick.expected_value > 0.03
    assert len(repo.shadows) == 1

def test_corner_engine_requires_supported_two_sided_total_market():
    repo = Repo(
        pairs=(
            market_pair(
                8,
                "Bet365",
                bet_id=101,
                bet_name="Asian Corners Handicap",
                line=10.5,
                over=2.20,
                under=1.65,
            ),
        )
    )

    result = _corner_engine(repo).run_fixture(fixture(), decision_at=NOW)

    assert result.decisions_inserted == 1
    assert result.picks_inserted == 0
    assert repo.decisions[0].reason == "NO_SUPPORTED_TOTAL_MARKET"


def _card_repo_with_total_cards() -> Repo:
    return Repo(
        pairs=(
            market_pair(
                11,
                "1xBet",
                bet_id=80,
                bet_name="Cards Over/Under",
                line=4.5,
                over=1.80,
                under=2.00,
            ),
        ),
        card_feature={
            "referee": "Ref Example",
            "referee_card_rate": 5.8,
            "referee_sample_size": 12,
            "referee_foul_rate": 24.0,
            "referee_foul_sample_size": 12,
            "derby_rivalry_indicator": 1,
            "table_pressure": 0.8,
            "match_importance": 0.7,
            "feature_version": "CARDLAB_FEATURES_V1",
        },
    )


def test_card_engine_uses_only_1xbet_and_its_own_poisson_probability():
    repo = _card_repo_with_total_cards()

    result = CardLabShadowPickEngine(repo).run_fixture(fixture(), decision_at=NOW)

    assert result.decisions_inserted == 2
    assert result.picks_inserted == 1
    pick = next(item for item in repo.decisions if item.decision == "PICK")
    assert pick.lab == "CARD"
    assert pick.market_key == "TOTAL_CARDS"
    assert pick.selection == "OVER"
    assert pick.bookmaker_id == 11
    assert pick.bookmaker_name == "1xBet"
    assert pick.reference_bookmaker_id is None
    assert pick.reference_bookmaker_name is None
    assert pick.reference_observation_id is None
    assert pick.reference_companion_observation_id is None
    assert pick.reference_odds is None
    assert pick.reference_companion_odds is None
    assert pick.details["card_context"]["referee_card_rate"] == 5.8
    assert pick.details["expected_total_cards"] == 5.8
    assert pick.details["probability_model"]["reference_bookmaker_used"] is False
    assert pick.details["settlement_contract"]["status"] == "VERIFIED_1XBET_TARGET"
    assert pick.model_probability > pick.market_probability
    assert {item.bookmaker_id for item in repo.decisions} == {11}


def test_card_engine_does_not_require_bet365_reference():
    repo = _card_repo_with_total_cards()

    result = CardLabShadowPickEngine(repo).run_fixture(fixture(), decision_at=NOW)

    assert result.decisions_inserted == 2
    assert result.picks_inserted == 1
    assert all(item.reference_bookmaker_id is None for item in repo.decisions)


def test_card_engine_passes_before_market_lookup_when_referee_sample_is_too_small():
    class NoMarketRepo(Repo):
        def total_market_pairs(self, *_args, **_kwargs):
            raise AssertionError("market lookup must not occur with insufficient referee history")

    repo = NoMarketRepo(
        card_feature={
            "referee": "New Ref",
            "referee_card_rate": 4.9,
            "referee_sample_size": 3,
            "feature_version": "CARDLAB_FEATURES_V1",
        }
    )

    result = CardLabShadowPickEngine(repo).run_fixture(fixture(), decision_at=NOW)

    assert result.decisions_inserted == 1
    assert result.picks_inserted == 0
    assert repo.decisions[0].reason == "INSUFFICIENT_REFEREE_HISTORY"


def test_runtime_evaluates_corner_and_card_after_api_budget_stops_collection():
    from types import SimpleNamespace

    from h2h.odds.budget import ApiBudgetExceededError
    from h2h.quantlab.runtime import QuantLabRuntime

    item = fixture()

    class BudgetRepo:
        def fixture_discovery_due(self, *_args, **_kwargs):
            return True

        def upcoming_fixtures(self, **_kwargs):
            return (item,)

        def market_labs_for_fixture(self, _fixture_id):
            return frozenset({"CORNER", "CARD"})

    class ExhaustedProvider:
        def fetch_fixtures_for_date(self, _fixture_date):
            raise ApiBudgetExceededError("exhausted")

    class Engine:
        def __init__(self):
            self.calls = []

        def run_fixture(self, target, *, decision_at):
            self.calls.append((target["fixture_id"], decision_at))
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
    assert corner.calls == [("api-football:3001", NOW)]
    assert card.calls == [("api-football:3001", NOW)]

def test_context_queue_is_broad_and_market_driven():
    from types import SimpleNamespace

    from h2h.quantlab.runtime import QuantLabRuntime, QuantLabRuntimeSettings

    lower = {
        **fixture(),
        "fixture_id": "api-football:low",
        "country": "Sweden",
        "competition_name": "Division 2 - Norrland",
    }

    class QueueRepo:
        def __init__(self):
            self.limits = []

        def upcoming_fixtures(self, *, limit, **_kwargs):
            self.limits.append(limit)
            return (lower,)

        def market_labs_for_fixture(self, fixture_id):
            assert fixture_id == "api-football:low"
            return frozenset({"CORNER"})

    class Engine:
        def __init__(self):
            self.calls = []

        def run_fixture(self, item, *, decision_at):
            self.calls.append(item["fixture_id"])
            return SimpleNamespace(decisions_inserted=1, picks_inserted=0)

    repo = QueueRepo()
    engine = Engine()
    runtime = QuantLabRuntime(
        repo,
        object(),
        settings=QuantLabRuntimeSettings(fixture_limit=1),
        clock=lambda: NOW,
    )

    decisions, picks = runtime._evaluate_context_picks(engine, "CORNER", NOW)

    assert decisions == 1
    assert picks == 0
    assert engine.calls == ["api-football:low"]
    assert repo.limits == [1]


def test_collection_allows_lower_league_and_only_fetches_card_context_when_market_exists():
    from h2h.quantlab.runtime import QuantLabRuntime, QuantLabRuntimeSettings

    lower = {
        **fixture(),
        "fixture_id": "api-football:low",
        "provider_fixture_id": 4001,
        "league_id": 100,
        "season": 2026,
        "home_team_id": 10,
        "away_team_id": 11,
        "country": "Sweden",
        "competition_name": "Division 2 - Norrland",
    }
    class QueueRepo:
        def __init__(self):
            self.limits = []
            self.context_checked = []

        def upcoming_fixtures(self, *, limit, **_kwargs):
            self.limits.append(limit)
            return (lower,)

        def market_capture_due(self, *_args, **_kwargs):
            return False

        def market_labs_for_fixture(self, fixture_id):
            assert fixture_id == "api-football:low"
            return frozenset({"CARD", "CORNER"})

        def context_due(self, fixture_id, **_kwargs):
            self.context_checked.append(fixture_id)
            return False

        def latest_context_before(self, fixture_id, **_kwargs):
            assert fixture_id == "api-football:low"
            return {
                "referee": "Ref",
                "kickoff_at": lower["kickoff_at"],
                "available_at": NOW - timedelta(minutes=1),
            }

        def latest_standings_before(self, *_args, **_kwargs):
            return {
                "available_at": NOW - timedelta(minutes=1),
                "raw_payload": {},
            }

        def feature_snapshot_due(self, *_args, **_kwargs):
            return False

    repo = QueueRepo()
    runtime = QuantLabRuntime(
        repo,
        object(),
        settings=QuantLabRuntimeSettings(fixture_limit=1),
        clock=lambda: NOW,
    )

    market_fixtures, card_snapshots = runtime._collect_upcoming(NOW)

    assert market_fixtures == 0
    assert card_snapshots == 0
    assert repo.context_checked == ["api-football:low"]
    assert repo.limits == [1, 1]


def test_runtime_settles_finished_corner_shadow_bets():
    from h2h.quantlab.runtime import QuantLabRuntime

    class SettlementRepo:
        def __init__(self):
            self.saved = []

        def corner_shadow_settlement_candidates(self, *, limit):
            assert limit == 500
            return (
                {
                    "shadow_bet_id": "quantlab-shadow-v1:" + "e" * 64,
                    "fixture_id": "api-football:settled",
                    "market_key": "TOTAL_CORNERS",
                    "selection": "OVER",
                    "line": 9.5,
                    "odds": 2.0,
                    "stake_minor": 10_000,
                    "result_observation_id": "fixture-result-observation-v1:" + "d" * 64,
                    "result_classification": "PLAYED_SETTLEABLE",
                    "provider_status": "FT",
                    "statistics_observation_id": "stats:settled",
                    "statistics_available_at": NOW,
                    "home_corner_kicks": 7,
                    "away_corner_kicks": 4,
                },
            )

        def save_corner_settlement_event(self, settlement):
            self.saved.append(settlement)
            return True

    repo = SettlementRepo()
    runtime = QuantLabRuntime(repo, object(), clock=lambda: NOW)

    assert runtime._settle_corner_picks(NOW) == 1
    assert repo.saved[0].outcome == "WIN"
    assert repo.saved[0].result_detail["actual_total_corners"] == 11



def test_runtime_captures_and_settles_finished_1xbet_card_shadow_bet():
    from h2h.quantlab.runtime import QuantLabRuntime

    class CardSettlementRepo:
        def __init__(self):
            self.observation = None
            self.settlement = None

        def card_event_capture_candidates(self, *, limit):
            assert limit == 25
            return (
                {
                    "fixture_id": "api-football:card-settled",
                    "provider_fixture_id": 999,
                    "provider_status": "FT",
                },
            )

        def save_card_event_observation(self, observation):
            self.observation = observation
            return True

        def card_shadow_settlement_candidates(self, *, limit):
            assert limit == 500
            assert self.observation is not None
            return (
                {
                    "shadow_bet_id": "quantlab-shadow-v1:" + "f" * 64,
                    "fixture_id": "api-football:card-settled",
                    "bookmaker_id": 11,
                    "provider_bet_id": 80,
                    "market_key": "TOTAL_CARDS",
                    "selection": "OVER",
                    "line": 2.5,
                    "odds": 1.9,
                    "stake_minor": 10_000,
                    "fixture_observation_id": "quantlab-fixture-v1:" + "e" * 64,
                    "provider_status": "FT",
                    "result_classification": "PLAYED_SETTLEABLE",
                    "card_event_observation_id": self.observation.card_event_observation_id,
                    "total_cards_1xbet": self.observation.total_cards_1xbet,
                },
            )

        def save_card_settlement_event(self, settlement):
            self.settlement = settlement
            return True

    class Provider:
        def fetch_events(self, fixture_id):
            assert fixture_id == 999
            return {
                "errors": [],
                "response": [
                    {
                        "time": {"elapsed": 10, "extra": None},
                        "team": {"id": 1},
                        "player": {"id": 10, "name": "A"},
                        "type": "Card",
                        "detail": "Yellow Card",
                    },
                    {
                        "time": {"elapsed": 40, "extra": None},
                        "team": {"id": 1},
                        "player": {"id": 11, "name": "B"},
                        "type": "Card",
                        "detail": "Yellow Card",
                    },
                    {
                        "time": {"elapsed": 80, "extra": None},
                        "team": {"id": 2},
                        "player": {"id": 12, "name": "C"},
                        "type": "Card",
                        "detail": "Red Card",
                    },
                ],
            }

    repo = CardSettlementRepo()
    runtime = QuantLabRuntime(repo, Provider(), clock=lambda: NOW)

    assert runtime._capture_card_pick_events(NOW) == 1
    assert runtime._settle_card_picks(NOW) == 1
    assert repo.observation.total_cards_1xbet == 3
    assert repo.settlement.outcome == "WIN"


def test_run_once_prioritizes_settlement_then_goallab_before_corner_enrichment():
    from h2h.quantlab.runtime import QuantLabRuntime

    order: list[str] = []
    runtime = QuantLabRuntime(
        object(),
        object(),
        goal_engine=object(),
        corner_engine=object(),
        card_engine=object(),
        clock=lambda: NOW,
    )

    def mark(name, value):
        def call(*_args, **_kwargs):
            order.append(name)
            return value

        return call

    runtime._refresh_corner_pick_results = mark("corner_result_refresh", 0)  # type: ignore[method-assign]
    runtime._refresh_corner_pick_statistics = mark("corner_stats_refresh", 0)  # type: ignore[method-assign]
    runtime._settle_corner_picks = mark("corner_settlement", 1)  # type: ignore[method-assign]
    runtime._refresh_card_pick_results = mark("card_result_refresh", 0)  # type: ignore[method-assign]
    runtime._capture_card_pick_events = mark("card_event_capture", 0)  # type: ignore[method-assign]
    runtime._settle_card_picks = mark("card_settlement", 1)  # type: ignore[method-assign]
    runtime._discover_fixtures = mark("discover", 0)  # type: ignore[method-assign]
    runtime._backfill_history = mark("history", 0)  # type: ignore[method-assign]
    runtime._collect_upcoming = mark("collect", (0, 0))  # type: ignore[method-assign]
    runtime._bootstrap_goal_team_history = mark("goal_history", (0, 0))  # type: ignore[method-assign]
    runtime._bootstrap_goal_player_history = mark("goal_players", 0)  # type: ignore[method-assign]
    runtime._bootstrap_corner_team_history = mark("corner_history", (0, 0))  # type: ignore[method-assign]

    def evaluate_context(_engine, lab, _now):
        order.append(f"{lab.lower()}_evaluation")
        return 0, 0

    runtime._evaluate_context_picks = evaluate_context  # type: ignore[method-assign]
    runtime._evaluate_goal_picks = mark("goal_evaluation", (0, 0))  # type: ignore[method-assign]
    runtime._settle_goal_picks = mark("goal_settlement", 0)  # type: ignore[method-assign]

    result = runtime.run_once()

    assert result["corner_settlements"] == 1
    assert result["card_settlements"] == 1
    assert order[:3] == [
        "corner_result_refresh",
        "corner_stats_refresh",
        "corner_settlement",
    ]
    assert order.index("corner_settlement") < order.index("card_result_refresh")
    assert order.index("card_settlement") < order.index("goal_evaluation")
    assert order.index("goal_evaluation") < order.index("goal_settlement")
    assert order.index("goal_settlement") < order.index("discover")
    assert order.index("collect") < order.index("goal_history")
    assert order.index("goal_history") < order.index("corner_history")
    assert order.index("corner_history") < order.index("corner_evaluation")
    assert order.index("corner_evaluation") < order.index("card_evaluation")
