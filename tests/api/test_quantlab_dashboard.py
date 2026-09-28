from datetime import UTC, datetime

from h2h.quantlab.dashboard import QuantLabDashboardService
from h2h.quantlab.repository import PostgreSQLQuantLabRepository


NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


class StubRepository:
    def __init__(self) -> None:
        self.labs: list[str] = []

    def list_bets(self, lab: str):
        self.labs.append(lab)
        return ()

    def list_goal_picks(self):
        self.labs.append("GOAL_PICKS")
        return (
            {
                "goal_pick_id": "quantlab-goal-pick-v1:" + "a" * 64,
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
                "policy_version": "GOALLAB_DC_PLUS_PICK_POLICY_V1",
                "model_probability": 0.58,
                "market_probability": 0.52,
                "edge": 0.06,
                "expected_value": 0.10,
                "expected_home_goals": 1.7,
                "expected_away_goals": 1.1,
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
                    "model_feature_names": (
                        "home_l5_goals_for",
                        "away_l5_goals_against",
                    ),
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
            },
        )

    def goal_model_contract(self, model_version=None):
        return {
            "model_version": "DC_PLUS_PRO_STRUCTURAL_V1:" + "b" * 64,
            "feature_version": "GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1",
            "training_sample_size": 500,
            "history_match_count": 800,
            "rho": -0.05,
            "active_feature_count": 2,
            "active_feature_names": ("home_l5_goals_for", "away_l5_goals_against"),
            "parameters": {
                "model_feature_names": (
                    "home_l5_goals_for",
                    "away_l5_goals_against",
                ),
                "base_feature_names": (
                    "home_l5_goals_for",
                    "away_l5_goals_against",
                ),
                "beta_home": [0.20, 0.10],
                "beta_away": [0.05, 0.30],
            },
            "feature_means": {
                "home_l5_goals_for": 1.50,
                "away_l5_goals_against": 1.20,
            },
            "feature_scales": {
                "home_l5_goals_for": 0.50,
                "away_l5_goals_against": 0.40,
            },
            "training_payload": {
                "contract_coverage": {
                    "B_RECENT_RESULT_GOAL_FORM": {
                        "status": "FULL",
                        "implemented": [11, 12],
                        "pending": [],
                    }
                }
            },
        }

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

    assert repository.labs == ["GOAL_PICKS"]
    assert "GoalLab" in html
    assert "CornerLab" in html
    assert "CardLab" in html
    assert "42 / 75,000" in html
    assert "300.00 RSD" in html
    assert "DC+ Pro Structural" in html
    assert "GoalLab canonical picks" in html
    assert "DC+ model contract / active variables" in html
    assert "home_l5_goals_for" in html
    assert "Sve analizirane utakmice · PASS + PICK" in html
    assert "EDGE_BELOW_MINIMUM" in html
    assert "SHADOW ONLY" in html
    assert "GoalLab Research / Audit" in html
    assert "same-page research view" in html
    assert "Open GoalLab Analytics V2" not in html
    assert 'title="Lowest first"' in html
    assert 'title="Highest first"' in html
    assert "/quantlab/goal/pick?" in html
    assert "/quantlab/goal/model?" in html
    assert "Izabrani pikovi · aktivni" in html
    assert "Sve analizirane utakmice · PASS + PICK" in html
    assert "📝" in html
    assert "Model je za Home – Away izabrao" in html
    assert "Forma golova L5: domaćin daje 2.10" in html
    assert "trening prosek 1.50" in html


def test_quantlab_dashboard_routes_corner_tab_to_corner_lab() -> None:
    class CornerRepository(StubRepository):
        def list_bets(self, lab: str):
            self.labs.append(lab)
            return (
                {
                    "shadow_bet_id": "quantlab-shadow-v1:" + "c" * 64,
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
                    "outcome": "WIN",
                    "pnl_minor": 10_000,
                    "settled_at": NOW,
                    "home_team": "Home",
                    "away_team": "Away",
                    "competition_name": "League",
                    "country": "England",
                    "kickoff_at": NOW,
                    "expected_total_corners": 11.2,
                    "home_history_size": 10,
                    "away_history_size": 9,
                    "corner_feature_payload": {
                        "raw_features": {
                            "home_l5_corners_for": 6.2,
                            "home_l5_corners_against": 4.0,
                            "away_l5_corners_for": 5.7,
                            "away_l5_corners_against": 4.5,
                            "home_l5_shots_for": 15.0,
                            "away_l5_shots_for": 13.0,
                            "home_l5_sot_for": 5.5,
                            "away_l5_sot_for": 4.8,
                        }
                    },
                },
            )

    repository = CornerRepository()
    html = QuantLabDashboardService(repository).render_html("lab=corner")

    assert repository.labs == ["CORNER"]
    assert "CornerLab pikovi · čekaju rezultat" in html
    assert "CornerLab kompletan pick / settlement ledger" in html
    assert '<div class="card"><small>Pikovi</small><b>1</b></div>' in html
    assert "Kako CornerLab dolazi do procene" in html
    assert "48 strukturnih varijabli" in html
    assert "kvote nisu model input" in html
    assert "📝" in html
    assert "Zašto ovaj pik" in html
    assert "Model očekuje 11.20 ukupnih kornera" in html
    assert "audit only" in html
    assert ">1-0<" in html


class FailingGoalRepository(StubRepository):
    def list_goal_picks(self):
        raise RuntimeError("ledger unavailable")

    def goal_model_contract(self):
        raise RuntimeError("contract unavailable")

    def list_goal_fixture_status(self, **_kwargs):
        raise RuntimeError("pipeline unavailable")


def test_goal_dashboard_degrades_instead_of_returning_render_failure() -> None:
    html = QuantLabDashboardService(FailingGoalRepository()).render_html("lab=goal")

    assert "GoalLab" in html
    assert "Canonical pick ledger temporarily unavailable." in html
    assert "DC+ model contract temporarily unavailable." in html
    assert "Upcoming GoalLab pipeline temporarily unavailable." in html
    assert "No GoalLab canonical picks yet" in html
    assert "No trained DC+ Structural artifact is stored yet." in html



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
            visible = dict(StubRepository.list_goal_picks(self)[0])
            older_loss = dict(visible)
            older_loss["goal_pick_id"] = "quantlab-goal-pick-v1:" + "f" * 64
            older_loss["fixture_id"] = "api-football:122"
            older_loss["outcome"] = "LOSS"
            older_loss["pnl_minor"] = -30_000
            older_loss["home_team"] = "Older"
            older_loss["away_team"] = "Loss"
            return (visible, older_loss)

    html = QuantLabDashboardService(CompleteHistoryRepository()).render_html("lab=goal")

    assert '<div class="card"><small>Canonical picks</small><b>2</b></div>' in html
    assert '<div class="card"><small>Settled</small><b>2</b></div>' in html
    assert '<div class="card"><small>ROI</small><b>+0.00%</b></div>' in html
    assert '<div class="card"><small>Win rate</small><b>50.0%</b></div>' in html
    assert "Older – Loss" not in html



def test_quantlab_kpis_flag_mixed_versions_and_can_filter_exact_regime() -> None:
    class MixedVersionRepository(StubRepository):
        def list_all_goal_picks(self):
            first = dict(StubRepository.list_goal_picks(self)[0])
            second = dict(first)
            second["goal_pick_id"] = "quantlab-goal-pick-v1:" + "9" * 64
            second["fixture_id"] = "api-football:999"
            second["model_version"] = "DC_PLUS_PRO_STRUCTURAL_V1:" + "8" * 64
            second["policy_version"] = "GOALLAB_DC_PLUS_PICK_POLICY_V2"
            second["outcome"] = "LOSS"
            second["pnl_minor"] = -30_000
            return (first, second)

    repository = MixedVersionRepository()
    dashboard = QuantLabDashboardService(repository)

    mixed_html = dashboard.render_html("lab=goal")
    assert "MIXED VERSION KPI" in mixed_html
    assert "Model versions: 2" in mixed_html
    assert "policy versions: 2" in mixed_html

    model_version = "DC_PLUS_PRO_STRUCTURAL_V1:" + "b" * 64
    filtered_html = dashboard.render_html(
        "lab=goal&model_version=" + model_version
        + "&policy_version=GOALLAB_DC_PLUS_PICK_POLICY_V1"
    )
    assert "SINGLE VERSION KPI" in filtered_html
    assert '<div class="card"><small>Canonical picks</small><b>1</b></div>' in filtered_html
    assert '<div class="card"><small>ROI</small><b>+100.00%</b></div>' in filtered_html


def test_goallab_same_page_research_cohort_drills_into_underlying_picks() -> None:
    class ResearchRepository(StubRepository):
        def list_all_goal_picks(self):
            first = dict(StubRepository.list_goal_picks(self)[0])
            first["feature_payload"] = {"raw_features": {"x": 1.0}}
            first["source_decision_id"] = "quantlab-goal-decision-v1:" + "1" * 64
            return (first,)

        def list_all_goal_decisions(self):
            return (
                {
                    "decision_id": "quantlab-goal-decision-v1:" + "1" * 64,
                    "fixture_id": "api-football:123",
                    "decision": "PICK",
                    "reason": "CANONICAL_FIXTURE_VALUE_PICK",
                    "model_version": "DC_PLUS_PRO_STRUCTURAL_V1:" + "b" * 64,
                    "policy_version": "GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V2",
                },
            )

    html = QuantLabDashboardService(ResearchRepository()).render_html(
        "lab=goal&research_table=league&research_sort=roi_pct&research_dir=desc"
    )

    assert 'id="research-overview"' in html
    assert 'id="research-league"' in html
    assert "click a value → underlying picks" in html
    assert "league=Premier+League" in html
    assert "#canonical-picks" in html
    assert "sort-active" in html


def test_goallab_ledger_sorting_highest_and_lowest() -> None:
    class SortRepository(StubRepository):
        def list_goal_picks(self):
            first = dict(StubRepository.list_goal_picks(self)[0])
            first["home_team"] = "Low"
            first["away_team"] = "Odds"
            first["odds"] = 1.60
            second = dict(first)
            second["goal_pick_id"] = "quantlab-goal-pick-v1:" + "7" * 64
            second["fixture_id"] = "api-football:999"
            second["home_team"] = "High"
            second["away_team"] = "Odds"
            second["odds"] = 2.40
            return (first, second)

        def list_all_goal_picks(self):
            return self.list_goal_picks()

    dashboard = QuantLabDashboardService(SortRepository())
    highest = dashboard.render_html("lab=goal&ledger_sort=odds&ledger_dir=desc")
    lowest = dashboard.render_html("lab=goal&ledger_sort=odds&ledger_dir=asc")

    assert highest.index("High – Odds") < highest.index("Low – Odds")
    assert lowest.index("Low – Odds") < lowest.index("High – Odds")
    assert 'ledger_sort=odds' in highest
    assert 'title="Highest first"' in highest
