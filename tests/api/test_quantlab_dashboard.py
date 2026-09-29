from datetime import UTC, datetime

from h2h.quantlab.dashboard import QuantLabDashboardService
from h2h.quantlab.repository import PostgreSQLQuantLabRepository


NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


def goal_pick(*, outcome: str = "WIN", suffix: str = "a"):
    return {
        "goal_pick_id": "quantlab-goal-pick-v1:" + suffix * 64,
        "fixture_id": "api-football:123",
        "bookmaker_id": 8,
        "bookmaker_name": "Bet365",
        "provider_bet_id": 5,
        "provider_bet_name": "Goals Over/Under",
        "market_key": "OU_25",
        "selection": "OVER",
        "line": 2.5,
        "model_name": "DC+ Pro Structural",
        "model_version": "DC_PLUS_PRO_STRUCTURAL_V1:" + "b" * 64,
        "policy_version": "GOALLAB_DC_PLUS_PICK_POLICY_V4",
        "pick_policy_version": "GOALLAB_DC_PLUS_PICK_POLICY_V4",
        "model_probability": 0.58,
        "market_probability": 0.52,
        "edge": 0.06,
        "expected_value": 0.10,
        "expected_home_goals": 1.72,
        "expected_away_goals": 1.08,
        "odds": 2.0,
        "quote_observed_at": NOW,
        "decision_at": NOW,
        "closing_odds": None,
        "closing_observed_at": None,
        "stake_minor": 30_000,
        "outcome": outcome,
        "pnl_minor": 30_000 if outcome == "WIN" else -30_000 if outcome == "LOSS" else None,
        "settled_at": NOW if outcome in {"WIN", "LOSS", "VOID"} else None,
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "Premier League",
        "country": "England",
        "kickoff_at": NOW,
        "feature_payload": {
            "raw_features": {
                "home_l5_goals_for": 2.10,
                "home_l5_goals_against": 1.00,
                "away_l5_goals_for": 1.20,
                "away_l5_goals_against": 1.60,
                "home_l5_shots_for": 14.0,
                "home_l5_sot_for": 5.4,
                "away_l5_shots_for": 10.2,
                "away_l5_sot_for": 3.6,
            },
            "target_match_live_stats_used": False,
        },
        "selection_rank_payload": {
            "candidate_count": 2,
            "candidates": [
                {
                    "rank": 1,
                    "bookmaker_name": "Bet365",
                    "market_key": "OU_25",
                    "selection": "OVER",
                }
            ],
        },
    }


def corner_pick(*, outcome: str = "WIN", suffix: str = "c"):
    return {
        "shadow_bet_id": "quantlab-shadow-v1:" + suffix * 64,
        "fixture_id": "api-football:777",
        "lab": "CORNER",
        "bookmaker_id": 8,
        "bookmaker_name": "Bet365",
        "provider_bet_id": 100,
        "provider_bet_name": "Corners Over Under",
        "market_key": "TOTAL_CORNERS",
        "selection": "OVER",
        "line": 9.5,
        "model_name": "Corner pressure Poisson GLM",
        "model_version": "CORNER_PRESSURE_POISSON_V1:" + "d" * 64,
        "policy_version": "CORNERLAB_PRESSURE_VALUE_POLICY_V2",
        "model_probability": 0.62,
        "market_probability": 0.48,
        "edge": 0.14,
        "expected_value": 0.24,
        "odds": 2.0,
        "quote_observed_at": NOW,
        "decision_at": NOW,
        "closing_odds": 1.95,
        "closing_observed_at": NOW,
        "stake_minor": 10_000,
        "outcome": outcome,
        "pnl_minor": 10_000 if outcome == "WIN" else -10_000 if outcome == "LOSS" else None,
        "settled_at": NOW if outcome in {"WIN", "LOSS", "VOID"} else None,
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "League",
        "country": "England",
        "kickoff_at": NOW,
        "corner_feature_payload": {"raw_features": {"home_l5_corners_for": 6.2}},
    }


class StubRepository:
    def __init__(self) -> None:
        self.labs: list[str] = []

    def list_bets(self, lab: str):
        self.labs.append(lab)
        return ()

    def list_goal_picks(self):
        self.labs.append("GOAL_PICKS")
        return (goal_pick(),)

    def api_usage_today(self) -> int:
        return 42


def test_quantlab_dashboard_is_operational_only() -> None:
    repository = StubRepository()
    html = QuantLabDashboardService(repository).render_html("lab=goal")

    assert repository.labs == ["GOAL_PICKS"]
    assert "GoalLab" in html
    assert "CornerLab" in html
    assert "CardLab" in html
    assert ">Dashboard<" in html
    assert ">Analytics<" in html
    assert "Active Picks" in html
    assert "Pick History" in html
    assert "42 / 75,000" in html
    assert "300.00 RSD" in html
    assert "WIN" in html
    assert "/quantlab/goal/pick?" in html
    assert "GoalLab Research / Audit" not in html
    assert "Sve analizirane utakmice · PASS + PICK" not in html
    assert "DC+ model contract / active variables" not in html


def test_goallab_dashboard_restores_plain_serbian_pick_notes() -> None:
    html = QuantLabDashboardService(StubRepository()).render_html("lab=goal")

    assert "<th>Notes</th>" in html
    assert "📝" in html
    assert "Zašto je izabran ovaj pik" in html
    assert "Model je za Home – Away izabrao „više od 2.5 gola“" in html
    assert "Forma golova L5: domaćin daje 2.10" in html
    assert "Šutevi L5: domaćin 14.00 šuteva / 5.40 u okvir" in html
    assert "Po aktuelnom V4 pravilu" in html
    assert "Edge pomaže pri rangiranju" in html
    assert "Među 2 kandidata koji su prošli filtere" in html
    assert "Nisu korišćene live statistike" in html
    assert "Otvori sve brojke i sve varijable →" in html


def test_quantlab_dashboard_separates_active_from_history() -> None:
    class ActiveRepository(StubRepository):
        def list_goal_picks(self):
            self.labs.append("GOAL_PICKS")
            pending = goal_pick(outcome="PENDING", suffix="p")
            pending["home_team"] = "Active"
            pending["away_team"] = "Match"
            settled = goal_pick(outcome="WIN", suffix="w")
            settled["home_team"] = "Settled"
            settled["away_team"] = "Match"
            return (pending, settled)

    html = QuantLabDashboardService(ActiveRepository()).render_html("lab=goal")

    active_section = html.split("<b>Active Picks</b>", 1)[1].split("<b>Pick History</b>", 1)[0]
    history_section = html.split("<b>Pick History</b>", 1)[1]
    assert "Active – Match" in active_section
    assert "Settled – Match" not in active_section
    assert "Settled – Match" in history_section
    assert "Active – Match" not in history_section
    assert html.count("📝") == 2
    assert "Zašto je izabran ovaj pik" in active_section
    assert "Zašto je izabran ovaj pik" in history_section


def test_quantlab_dashboard_routes_corner_tab_to_corner_lab() -> None:
    class CornerRepository(StubRepository):
        def list_bets(self, lab: str):
            self.labs.append(lab)
            return (corner_pick(),)

    repository = CornerRepository()
    html = QuantLabDashboardService(repository).render_html("lab=corner")

    assert repository.labs == ["CORNER"]
    assert "CornerLab" in html
    assert "Active Picks" in html
    assert "Pick History" in html
    assert "TOTAL_CORNERS · OVER 9.5" in html
    assert "WIN" in html
    assert "Kako CornerLab dolazi do procene" not in html
    assert "<th>Notes</th>" not in html
    assert "📝" not in html


class FailingGoalRepository(StubRepository):
    def list_goal_picks(self):
        raise RuntimeError("ledger unavailable")


def test_goal_dashboard_degrades_instead_of_returning_render_failure() -> None:
    html = QuantLabDashboardService(FailingGoalRepository()).render_html("lab=goal")

    assert "GoalLab" in html
    assert "Pick ledger temporarily unavailable." in html
    assert "No active picks." in html
    assert "No settled picks yet." in html


def test_quantlab_repository_pages_complete_histories_for_metrics() -> None:
    repository = PostgreSQLQuantLabRepository(connect=lambda: None)

    bet_calls: list[tuple[str, int, int]] = []

    def bet_page(
        lab: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[dict[str, str], ...]:
        bet_calls.append((lab, limit, offset))
        pages = {
            0: ({"fixture_id": "1"}, {"fixture_id": "2"}),
            2: ({"fixture_id": "3"},),
        }
        return pages.get(offset, ())

    repository.list_bets = bet_page  # type: ignore[method-assign]

    assert repository.list_all_bets("CORNER", batch_size=2) == (
        {"fixture_id": "1"},
        {"fixture_id": "2"},
        {"fixture_id": "3"},
    )
    assert bet_calls == [("CORNER", 2, 0), ("CORNER", 2, 2)]

    goal_calls: list[tuple[int, int]] = []

    def goal_page(
        *,
        limit: int,
        offset: int,
    ) -> tuple[dict[str, str], ...]:
        goal_calls.append((limit, offset))
        pages = {
            0: ({"fixture_id": "10"}, {"fixture_id": "11"}),
            2: ({"fixture_id": "12"},),
        }
        return pages.get(offset, ())

    repository.list_goal_picks = goal_page  # type: ignore[method-assign]

    assert repository.list_all_goal_picks(batch_size=2) == (
        {"fixture_id": "10"},
        {"fixture_id": "11"},
        {"fixture_id": "12"},
    )
    assert goal_calls == [(2, 0), (2, 2)]


def test_quantlab_kpis_use_complete_history_not_latest_display_page() -> None:
    class CompleteHistoryRepository(StubRepository):
        def list_all_goal_picks(self):
            visible = goal_pick(outcome="WIN", suffix="v")
            older_loss = goal_pick(outcome="LOSS", suffix="l")
            older_loss["fixture_id"] = "api-football:122"
            older_loss["home_team"] = "Older"
            older_loss["away_team"] = "Loss"
            return (visible, older_loss)

    html = QuantLabDashboardService(CompleteHistoryRepository()).render_html("lab=goal")

    assert '<div class="card"><small>Settled</small><b>2</b></div>' in html
    assert '<div class="card"><small>Wins</small><b>1</b></div>' in html
    assert '<div class="card"><small>Losses</small><b>1</b></div>' in html
    assert '<div class="card"><small>ROI</small><b>+0.00%</b></div>' in html
    assert "Older – Loss" not in html


def test_goallab_analytics_is_a_separate_tab() -> None:
    class ResearchRepository(StubRepository):
        def list_all_goal_picks(self):
            first = goal_pick()
            first["source_decision_id"] = "quantlab-goal-decision-v1:" + "1" * 64
            return (first,)

        def list_all_goal_decisions(self):
            return (
                {
                    "decision_id": "quantlab-goal-decision-v1:" + "1" * 64,
                    "fixture_id": "api-football:123",
                    "decision": "PICK",
                    "reason": "CANONICAL_FIXTURE_VALUE_PICK",
                    "model_version": first_model_version(),
                    "policy_version": "GOALLAB_DC_PLUS_PICK_POLICY_V1",
                },
            )

    dashboard = QuantLabDashboardService(ResearchRepository())
    operational = dashboard.render_html("lab=goal")
    analytics = dashboard.render_html("view=analytics&lab=goal")

    assert "GoalLab Research / Audit" not in operational
    assert "GoalLab Analytics" in analytics
    assert "Markets / selections" in analytics
    assert "Leagues" in analytics
    assert "Bookmakers" in analytics
    assert "Model versions" in analytics
    assert "Calibration" in analytics
    assert "GoalLab Research / Audit" in analytics
    assert "CANONICAL_FIXTURE_VALUE_PICK" in analytics
    assert "Active Picks" not in analytics
    assert "Pick History" not in analytics


def first_model_version() -> str:
    return "DC_PLUS_PRO_STRUCTURAL_V1:" + "b" * 64


def test_cornerlab_has_dedicated_analytics_tab() -> None:
    class CornerRepository(StubRepository):
        def list_bets(self, lab: str):
            self.labs.append(lab)
            return (corner_pick(),)

        def list_all_bets(self, lab: str):
            return (corner_pick(),)

    html = QuantLabDashboardService(CornerRepository()).render_html(
        "view=analytics&lab=corner"
    )

    assert "CornerLab Analytics" in html
    assert "Markets / selections" in html
    assert "Leagues" in html
    assert "Bookmakers" in html
    assert "Model versions" in html
    assert "Calibration" in html
    assert "GoalLab Research / Audit" not in html
    assert ">CardLab<" not in html


def test_cardlab_does_not_get_an_analytics_surface_yet() -> None:
    html = QuantLabDashboardService(StubRepository()).render_html(
        "view=analytics&lab=card"
    )

    assert "GoalLab Analytics" in html
    assert ">CardLab<" not in html
