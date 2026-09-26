from datetime import UTC, datetime

from h2h.quantlab.dashboard import QuantLabDashboardService


NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


class StubRepository:
    def __init__(self) -> None:
        self.labs: list[str] = []

    def list_bets(self, lab: str):
        self.labs.append(lab)
        if lab != "GOAL":
            return ()
        return (
            {
                "shadow_bet_id": "quantlab-shadow-v1:" + "a" * 64,
                "fixture_id": "api-football:123",
                "lab": "GOAL",
                "bookmaker_id": 8,
                "bookmaker_name": "Bet365",
                "provider_bet_id": 5,
                "provider_bet_name": "Goals Over/Under",
                "market_key": "OU_2_5",
                "selection": "OVER",
                "line": 2.5,
                "model_name": "DC+ Core",
                "model_version": "v1",
                "model_probability": 0.58,
                "market_probability": 0.52,
                "edge": 0.06,
                "expected_value": 0.10,
                "odds": 2.0,
                "quote_observed_at": NOW,
                "decision_at": NOW,
                "closing_odds": None,
                "closing_observed_at": None,
                "stake_minor": 30000,
                "outcome": "WIN",
                "pnl_minor": 30000,
                "settled_at": NOW,
                "home_team": "Home",
                "away_team": "Away",
                "competition_name": "Premier League",
                "country": "England",
                "kickoff_at": NOW,
            },
        )

    def api_usage_today(self) -> int:
        return 42

    def list_goal_fixture_status(self, **_kwargs):
        return (
            {
                "fixture_id": "api-football:124",
                "league_id": 39,
                "season": 2026,
                "home_team_id": 10,
                "away_team_id": 20,
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "competition_name": "Premier League",
                "country": "England",
                "competition_type": "League",
                "kickoff_at": NOW,
                "provider_status": "NS",
                "market_captured_at": NOW,
                "decision_at": NOW,
                "decision": "PASS",
                "reason": "EDGE_BELOW_MINIMUM",
                "model_version": "dc-v1",
                "market_key": "OU_25",
                "selection": "OVER",
                "bookmaker_name": "Bet365",
                "odds": 1.95,
                "edge": 0.01,
                "expected_value": 0.01,
            },
        )


def test_quantlab_dashboard_renders_three_labs_and_goal_metrics() -> None:
    repository = StubRepository()
    html = QuantLabDashboardService(repository).render_html("lab=goal")

    assert repository.labs == ["GOAL"]
    assert "GoalLab" in html
    assert "CornerLab" in html
    assert "CardLab" in html
    assert "42 / 1,000" in html
    assert "300.00 RSD" in html
    assert "DC+ Core" in html
    assert "Upcoming fixture / GoalLab decision pipeline" in html
    assert "EDGE_BELOW_MINIMUM" in html
    assert "SHADOW ONLY" in html


def test_quantlab_dashboard_routes_corner_tab_to_corner_lab() -> None:
    repository = StubRepository()
    html = QuantLabDashboardService(repository).render_html("lab=corner")

    assert repository.labs == ["CORNER"]
    assert "CornerLab shadow ledger" in html
    assert "No CornerLab shadow bets yet" in html
