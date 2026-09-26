from __future__ import annotations

from datetime import UTC, datetime, timedelta


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


def test_corner_engine_uses_cross_book_reference_and_creates_one_directional_pick():
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
            market_pair(
                11,
                "1xBet",
                bet_id=100,
                bet_name="Total Corners",
                line=10.5,
                over=1.80,
                under=2.00,
            ),
        )
    )

    result = CornerLabShadowPickEngine(repo).run_fixture(fixture(), decision_at=NOW)

    assert result.decisions_inserted == 4
    assert result.picks_inserted == 1
    pick = next(item for item in repo.decisions if item.decision == "PICK")
    assert pick.lab == "CORNER"
    assert pick.market_key == "TOTAL_CORNERS"
    assert pick.selection == "OVER"
    assert pick.bookmaker_id == 8
    assert pick.reference_bookmaker_id == 11
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

    result = CornerLabShadowPickEngine(repo).run_fixture(fixture(), decision_at=NOW)

    assert result.decisions_inserted == 1
    assert result.picks_inserted == 0
    assert repo.decisions[0].reason == "NO_SUPPORTED_TOTAL_MARKET"


def test_card_engine_requires_referee_history_and_direction_agreement():
    repo = Repo(
        pairs=(
            market_pair(
                8,
                "Bet365",
                bet_id=200,
                bet_name="Total Cards",
                line=4.5,
                over=2.20,
                under=1.65,
            ),
            market_pair(
                11,
                "1xBet",
                bet_id=200,
                bet_name="Total Cards",
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

    result = CardLabShadowPickEngine(repo).run_fixture(fixture(), decision_at=NOW)

    assert result.decisions_inserted == 4
    assert result.picks_inserted == 1
    pick = next(item for item in repo.decisions if item.decision == "PICK")
    assert pick.lab == "CARD"
    assert pick.market_key == "TOTAL_CARDS"
    assert pick.selection == "OVER"
    assert pick.details["card_context"]["referee_card_rate"] == 5.8
    under_reasons = {
        item.reason for item in repo.decisions if item.selection == "UNDER"
    }
    assert "REFEREE_RATE_DIRECTION_DISAGREES" in under_reasons


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
    top = {
        **fixture(),
        "fixture_id": "api-football:top",
        "provider_fixture_id": 4002,
        "league_id": 39,
        "season": 2026,
        "home_team_id": 12,
        "away_team_id": 13,
        "country": "England",
        "competition_name": "Premier League",
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
