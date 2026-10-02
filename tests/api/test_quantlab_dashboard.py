from datetime import UTC, datetime

from h2h.quantlab.dashboard import QuantLabDashboardService
from h2h.quantlab.dashboard_views import _dedupe_corner_settlements
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
                "home_l10_goals_for": 1.70,
                "away_l10_goals_for": 1.10,
                "home_venue_l5_goals_for": 2.30,
                "away_venue_l5_goals_for": 1.00,
                "home_l5_shots_for": 14.0,
                "home_l10_shots_for": 12.0,
                "home_l5_sot_for": 5.4,
                "home_l10_sot_for": 4.5,
                "away_l5_shots_for": 10.2,
                "away_l10_shots_for": 9.5,
                "away_l5_sot_for": 3.6,
                "away_l10_sot_for": 3.2,
                "home_history_match_count": 28,
                "away_history_match_count": 24,
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
        "expected_total_corners": 10.8,
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
        "home_history_size": 32,
        "away_history_size": 29,
        "corner_feature_payload": {
            "raw_features": {
                "home_l5_corners_for": 6.2,
                "home_l5_corners_against": 4.5,
                "away_l5_corners_for": 5.4,
                "away_l5_corners_against": 5.8,
                "home_l10_corners_for": 5.6,
                "away_l10_corners_for": 5.0,
                "home_venue_l5_corners_for": 6.5,
                "away_venue_l5_corners_for": 5.1,
                "home_l5_shots_for": 14.0,
                "home_l10_shots_for": 12.8,
                "away_l5_shots_for": 11.5,
                "away_l10_shots_for": 10.9,
                "home_l5_sot_for": 5.0,
                "home_l10_sot_for": 4.3,
                "away_l5_sot_for": 4.1,
                "away_l10_sot_for": 3.8,
            }
        },
    }


def test_cornerlab_legacy_settlement_dedupe_keeps_pick_closest_to_two() -> None:
    candidates = []
    for suffix, odds, outcome in (
        ("a", 1.55, "WIN"),
        ("b", 1.88, "LOSS"),
        ("c", 2.04, "WIN"),
        ("d", 2.35, "LOSS"),
    ):
        row = corner_pick(outcome=outcome, suffix=suffix)
        row["odds"] = odds
        candidates.append(row)

    pending = corner_pick(outcome="PENDING", suffix="p")
    pending["fixture_id"] = "api-football:778"

    result = _dedupe_corner_settlements(tuple((*candidates, pending)))
    settled = [row for row in result if row["outcome"] in {"WIN", "LOSS", "VOID"}]

    assert len(settled) == 1
    assert settled[0]["odds"] == 2.04
    assert pending in result


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


def test_cornerlab_dashboard_and_analytics_use_deduped_settlements() -> None:
    class LegacyCornerRepository(StubRepository):
        @staticmethod
        def _rows():
            rows = []
            for suffix, odds, home in (
                ("a", 1.55, "Far 155"),
                ("b", 1.88, "Near 188"),
                ("c", 2.04, "Closest 204"),
                ("d", 2.35, "Far 235"),
            ):
                row = corner_pick(outcome="WIN", suffix=suffix)
                row["odds"] = odds
                row["home_team"] = home
                rows.append(row)
            return tuple(rows)

        def list_bets(self, lab: str):
            assert lab == "CORNER"
            return self._rows()

        def list_all_bets(self, lab: str):
            assert lab == "CORNER"
            return self._rows()

    dashboard = QuantLabDashboardService(LegacyCornerRepository())
    home = dashboard.render_html("lab=corner")
    analytics = dashboard.render_html("view=analytics&lab=corner")

    history = home.split("<b>Pick History</b>", 1)[1]
    assert "Closest 204 – Away" in history
    assert "Near 188 – Away" not in history
    assert "Far 155 – Away" not in history
    assert "Far 235 – Away" not in history
    assert '<small>Settled</small><b>1</b>' in home
    assert '<small>Settled</small><b>1</b>' in analytics


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


def test_cardlab_dashboard_shows_pick_explanation_notes() -> None:
    class CardRepository(StubRepository):
        def list_bets(self, lab: str):
            self.labs.append(lab)
            row = corner_pick(outcome="PENDING", suffix="k")
            row.update(
                {
                    "lab": "CARD",
                    "fixture_id": "api-football:909",
                    "home_team": "Cards Home",
                    "away_team": "Cards Away",
                    "provider_bet_id": 80,
                    "provider_bet_name": "Cards Over/Under",
                    "market_key": "TOTAL_CARDS",
                    "selection": "OVER",
                    "line": 4.5,
                    "model_name": "CardLab raw-stat consensus",
                    "model_version": "CARDLAB_RAW_STATS_V1",
                    "policy_version": "CARDLAB_RAW_STATS_POLICY_V7_REFEREE_WEB",
                    "model_probability": 0.60,
                    "market_probability": 0.75,
                    "edge": -0.15,
                    "expected_value": -0.28,
                    "odds": 1.20,
                    "decision_reason": "RAW_STAT_CONSENSUS_PICK",
                    "decision_details": {
                        "raw_signal": {
                            "consensus_cards": 5.2,
                            "line_gap": 0.7,
                            "anchor_count": 5,
                            "directional_support": 0.60,
                            "observed_hit_rate": 0.55,
                        },
                        "card_context": {
                            "referee": "Ref Example",
                            "referee_card_rate": 5.8,
                            "referee_sample_size": 12,
                            "referee_foul_rate": 24.0,
                            "referee_foul_sample_size": 12,
                            "derby_rivalry_indicator": 1,
                            "home_table_pressure": 0.8,
                            "away_table_pressure": 0.7,
                            "match_importance": 0.75,
                            "feature_payload": {
                                "raw_features": {
                                    "raw_consensus_cards": 5.2,
                                    "raw_anchor_count": 5,
                                    "referee_l5_cards": 5.6,
                                    "referee_l10_cards": 5.8,
                                    "referee_l10_fouls": 24.0,
                                    "referee_l10_cards_per_foul": 0.24,
                                    "home_l10_cards_for": 2.7,
                                    "away_l10_cards_for": 2.5,
                                    "combined_team_cards_for_l10": 5.2,
                                    "matchup_expected_cards_l10": 5.1,
                                    "combined_fouls_committed_l10": 27.0,
                                    "h2h_total_cards_l5": 5.4,
                                    "league_total_cards": 4.9,
                                    "match_importance": 0.75,
                                    "table_pressure": 0.8,
                                    "market_one_x_two_balance": 0.86,
                                }
                            },
                        },
                        "raw_stat_policy": {
                            "price_independent_selection": True,
                            "ev_is_pick_gate": False,
                            "edge_is_pick_gate": False,
                            "odds_is_pick_gate": False,
                        },
                        "thresholds": {
                            "minimum_raw_anchors": 3,
                            "minimum_directional_support": 0.60,
                            "minimum_abs_line_gap": 0.35,
                        },
                    },
                }
            )
            return (row,)

    repository = CardRepository()
    html = QuantLabDashboardService(repository).render_html("lab=card")

    assert repository.labs == ["CARD"]
    assert "<th>Notes</th>" in html
    assert "📝" in html
    assert "Zašto ovaj CardLab raw-stat pik" in html
    assert "Ref Example" in html
    assert "raw consensus 5.20 kartona" in html
    assert "Timovi: home L10 2.70" in html
    assert "H2H 5.40" in html
    assert "EV, edge i raspon kvota" in html
    assert "ne odlučuju da li je nešto PICK" in html


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
    assert "Watchlist · ROI discovery" in analytics
    assert "Goal shape × price" in analytics
    assert "Balance × total-line gap" in analytics
    assert "Model vs market × price" in analytics
    assert "Trend × matchup" in analytics
    assert "Reliability × market" in analytics
    assert "λ min" in analytics
    assert "λ balance" in analytics
    assert "L5−L10 goals" in analytics
    assert "Missing features" in analytics
    assert "Markets / selections" in analytics
    assert "Leagues" in analytics
    assert "Bookmakers" in analytics
    assert "Entry odds" in analytics
    assert "Expected value" in analytics
    assert "Weekly stability" in analytics
    assert "Decision lead time" in analytics
    assert "Expected total goals" in analytics
    assert "Home − away expected-goal spread" in analytics
    assert "Calibration" in analytics
    assert "GoalLab Research / Audit" in analytics
    assert "CANONICAL_FIXTURE_VALUE_PICK" in analytics

    # Singleton/non-actionable and duplicated tables are intentionally omitted.
    assert "Countries" not in analytics
    assert "Closing odds" not in analytics
    assert "Market × selection × entry odds" not in analytics
    assert "Research-style signal cube" not in analytics
    assert "Recorded pre-match features" not in analytics
    assert "Home L5 goals for" not in analytics
    assert "Kickoff weekday" not in analytics
    assert "Kickoff time · Europe/Belgrade" not in analytics
    assert "Quote age at decision" not in analytics
    assert "Model versions" not in analytics
    assert "Policy versions" not in analytics
    assert "Model × policy" not in analytics

    assert analytics.index("Watchlist · ROI discovery") < analytics.index("Last 7 days")
    assert analytics.index("Watchlist · ROI discovery") < analytics.index("Universe / regimes")
    assert "Active Picks" not in analytics
    assert "Pick History" not in analytics



def test_quantlab_analytics_bucket_links_open_exact_settled_picks() -> None:
    class BucketRepository(StubRepository):
        def list_all_goal_picks(self):
            winner = goal_pick(outcome="WIN", suffix="w")
            winner["fixture_id"] = "api-football:201"
            winner["home_team"] = "Winner"
            winner["away_team"] = "Group"

            void = goal_pick(outcome="VOID", suffix="v")
            void["fixture_id"] = "api-football:202"
            void["home_team"] = "Void"
            void["away_team"] = "Group"

            pending = goal_pick(outcome="PENDING", suffix="p")
            pending["fixture_id"] = "api-football:203"
            pending["home_team"] = "Pending"
            pending["away_team"] = "Group"

            other = goal_pick(outcome="LOSS", suffix="u")
            other["fixture_id"] = "api-football:204"
            other["home_team"] = "Other"
            other["away_team"] = "Group"
            other["selection"] = "UNDER"

            return (winner, void, pending, other)

        def list_all_goal_decisions(self):
            return ()

    dashboard = QuantLabDashboardService(BucketRepository())
    analytics = dashboard.render_html("view=analytics&lab=goal")

    assert "<th>Picks</th>" not in analytics
    assert 'class="group-link"' in analytics
    assert "bucket_market_key=OU_25" in analytics
    assert "bucket_selection=OVER" in analytics
    assert "View 2" not in analytics
    assert "bucket_probability_bin=5" in analytics
    assert 'id="analytics-markets"' in analytics
    assert 'class="sort-header active"' in analytics
    assert '<span class="sort-arrow">↓</span>' in analytics

    drilldown = dashboard.render_html(
        "view=analytics&lab=goal&bucket=1&bucket_market_key=OU_25&bucket_selection=OVER"
    )

    assert "Bucket picks" in drilldown
    assert "2 exact settled picks" in drilldown
    assert "Winner – Group" in drilldown
    assert "Void – Group" in drilldown
    assert "Pending – Group" not in drilldown
    assert "Other – Group" not in drilldown


def test_quantlab_analytics_sorting_persists_and_keeps_zero_sample_groups_last() -> None:
    class SortRepository(StubRepository):
        def list_all_goal_picks(self):
            loss = goal_pick(outcome="LOSS", suffix="l")
            loss["fixture_id"] = "api-football:401"
            loss["competition_name"] = "Alpha League"
            loss["home_team"] = "Alpha"
            loss["away_team"] = "Loss"

            win = goal_pick(outcome="WIN", suffix="w")
            win["fixture_id"] = "api-football:402"
            win["competition_name"] = "Zulu League"
            win["home_team"] = "Zulu"
            win["away_team"] = "Win"

            pending = goal_pick(outcome="PENDING", suffix="p")
            pending["fixture_id"] = "api-football:403"
            pending["competition_name"] = "Pending League"
            pending["home_team"] = "Pending"
            pending["away_team"] = "Only"

            return (loss, win, pending)

        def list_all_goal_decisions(self):
            return ()

    html = QuantLabDashboardService(SortRepository()).render_html(
        "view=analytics&lab=goal&leagues_sort=roi_pct&leagues_dir=asc"
    )

    leagues = html.split('id="analytics-leagues"', 1)[1].split(
        'id="analytics-bookmakers"', 1
    )[0]
    assert leagues.index("Alpha League") < leagues.index("Zulu League")
    assert leagues.index("Zulu League") < leagues.index("Pending League")
    assert "leagues_sort=roi_pct" in leagues
    assert "leagues_dir=desc" in leagues
    assert '<span class="sort-arrow">↑</span>' in leagues


def test_quantlab_group_drilldown_link_preserves_table_sort_state() -> None:
    class SortedLinkRepository(StubRepository):
        def list_all_goal_picks(self):
            return (goal_pick(outcome="WIN", suffix="s"),)

        def list_all_goal_decisions(self):
            return ()

    html = QuantLabDashboardService(SortedLinkRepository()).render_html(
        "view=analytics&lab=goal&markets_sort=roi_pct&markets_dir=asc"
    )

    markets = html.split('id="analytics-markets"', 1)[1].split(
        'id="analytics-leagues"', 1
    )[0]
    assert "markets_sort=roi_pct" in markets
    assert "markets_dir=asc" in markets
    assert "bucket_market_key=OU_25" in markets
    assert "bucket_selection=OVER" in markets


def test_quantlab_research_style_numeric_bucket_drilldown_is_exact() -> None:
    class NumericBucketRepository(StubRepository):
        def list_all_goal_picks(self):
            in_bucket = goal_pick(outcome="WIN", suffix="i")
            in_bucket["fixture_id"] = "api-football:501"
            in_bucket["home_team"] = "Odds In"
            in_bucket["odds"] = 1.95

            out_bucket = goal_pick(outcome="LOSS", suffix="o")
            out_bucket["fixture_id"] = "api-football:502"
            out_bucket["home_team"] = "Odds Out"
            out_bucket["odds"] = 2.20

            return (in_bucket, out_bucket)

        def list_all_goal_decisions(self):
            return ()

    dashboard = QuantLabDashboardService(NumericBucketRepository())
    analytics = dashboard.render_html("view=analytics&lab=goal")

    assert "Entry odds" in analytics
    assert "bucket_entry_odds_bucket=" in analytics
    assert "Avg CLV" in analytics
    assert "CLV cov" in analytics
    assert "Max DD" in analytics

    drilldown = dashboard.render_html(
        "view=analytics&lab=goal&bucket=1&bucket_entry_odds_bucket=1.81–2.00"
    )

    assert "1 exact settled picks" in drilldown
    assert "Odds In" in drilldown
    assert "Odds Out" not in drilldown


def test_quantlab_goal_model_state_bucket_drilldown_is_exact() -> None:
    class GoalStateRepository(StubRepository):
        def list_all_goal_picks(self):
            low = goal_pick(outcome="WIN", suffix="g")
            low["fixture_id"] = "api-football:511"
            low["home_team"] = "Goal State In"
            low["expected_home_goals"] = 1.1
            low["expected_away_goals"] = 1.0

            high = goal_pick(outcome="LOSS", suffix="h")
            high["fixture_id"] = "api-football:512"
            high["home_team"] = "Goal State Out"
            high["expected_home_goals"] = 2.2
            high["expected_away_goals"] = 1.7

            return (low, high)

        def list_all_goal_decisions(self):
            return ()

    dashboard = QuantLabDashboardService(GoalStateRepository())
    html = dashboard.render_html(
        "view=analytics&lab=goal&bucket=1&bucket_expected_total_goals_bucket=2–2.5"
    )

    assert "1 exact settled picks" in html
    assert "Goal State In" in html
    assert "Goal State Out" not in html


def test_quantlab_watchlist_goal_shape_drilldown_is_exact() -> None:
    class WatchlistRepository(StubRepository):
        def list_all_goal_picks(self):
            matching = goal_pick(outcome="WIN", suffix="m")
            matching["fixture_id"] = "api-football:601"
            matching["home_team"] = "Watch In"
            matching["expected_home_goals"] = 1.72
            matching["expected_away_goals"] = 1.08
            matching["odds"] = 1.95

            other = goal_pick(outcome="LOSS", suffix="x")
            other["fixture_id"] = "api-football:602"
            other["home_team"] = "Watch Out"
            other["expected_home_goals"] = 2.30
            other["expected_away_goals"] = 1.40
            other["odds"] = 2.20

            return (matching, other)

        def list_all_goal_decisions(self):
            return ()

    dashboard = QuantLabDashboardService(WatchlistRepository())
    analytics = dashboard.render_html("view=analytics&lab=goal")

    assert 'id="analytics-watchlist"' in analytics
    assert "bucket_goal_lambda_min_bucket=" in analytics
    assert "bucket_expected_total_goals_bucket=" in analytics

    drilldown = dashboard.render_html(
        "view=analytics&lab=goal"
        "&bucket=1"
        "&bucket_market_key=OU_25"
        "&bucket_selection=OVER"
        "&bucket_expected_total_goals_bucket=2.5–3"
        "&bucket_goal_lambda_min_bucket=1–1.3"
        "&bucket_entry_odds_bucket=1.81–2.00"
    )

    assert "1 exact settled picks" in drilldown
    assert "Watch In" in drilldown
    assert "Watch Out" not in drilldown


def test_quantlab_calibration_bucket_drilldown_matches_graded_population() -> None:
    class CalibrationRepository(StubRepository):
        def list_all_goal_picks(self):
            win = goal_pick(outcome="WIN", suffix="w")
            win["fixture_id"] = "api-football:301"
            win["home_team"] = "Calibration Win"
            win["model_probability"] = 0.58

            loss = goal_pick(outcome="LOSS", suffix="l")
            loss["fixture_id"] = "api-football:302"
            loss["home_team"] = "Calibration Loss"
            loss["model_probability"] = 0.59

            void = goal_pick(outcome="VOID", suffix="v")
            void["fixture_id"] = "api-football:303"
            void["home_team"] = "Calibration Void"
            void["model_probability"] = 0.57

            return (win, loss, void)

        def list_all_goal_decisions(self):
            return ()

    html = QuantLabDashboardService(CalibrationRepository()).render_html(
        "view=analytics&lab=goal&bucket=1&bucket_probability_bin=5"
    )

    assert "2 exact settled picks" in html
    assert "Calibration Win" in html
    assert "Calibration Loss" in html
    assert "Calibration Void" not in html


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
    assert "Watchlist · ROI discovery" in html
    assert "Calibration watch · line × price" in html
    assert "Watch regime" in html
    assert "OVER model P 60–70%" in html
    assert "Model-line gap × price" in html
    assert "Pressure trend × matchup" in html
    assert "Model vs market × price" in html
    assert "Reliability × market" in html
    assert "L5−L10 corners" in html
    assert "Venue−L10" in html
    assert "Matchup pressure" in html
    assert "Markets / selections" in html
    assert "Leagues" in html
    assert "Bookmakers" in html
    assert "Entry odds" in html
    assert "Expected value" in html
    assert "Expected total corners" in html
    assert "Calibration" in html

    # Removed because the watchlist supersedes these noisy/duplicated views.
    assert "Countries" not in html
    assert "Expected corners − line" not in html
    assert "Market × expected total corners" not in html
    assert "Recorded pre-match features" not in html
    assert "Home L5 corners for" not in html
    assert "Kickoff weekday" not in html
    assert "Quote age at decision" not in html
    assert "Model versions" not in html
    assert "Policy versions" not in html
    assert "GoalLab Research / Audit" not in html
    assert ">CardLab<" in html

    assert html.index("Watchlist · ROI discovery") < html.index("Last 7 days")



def test_cornerlab_calibration_watchlist_drilldown_is_exact() -> None:
    class CornerWatchRepository(StubRepository):
        def list_all_bets(self, lab: str):
            matching = corner_pick(outcome="WIN", suffix="u")
            matching["fixture_id"] = "api-football:801"
            matching["home_team"] = "Corner Watch In"
            matching["selection"] = "UNDER"
            matching["line"] = 8.5
            matching["model_probability"] = 0.56
            matching["market_probability"] = 0.52
            matching["odds"] = 1.95

            other = corner_pick(outcome="LOSS", suffix="o")
            other["fixture_id"] = "api-football:802"
            other["home_team"] = "Corner Watch Out"
            other["selection"] = "OVER"
            other["line"] = 11.5
            other["model_probability"] = 0.55
            other["market_probability"] = 0.50
            other["odds"] = 1.95
            return (matching, other)

    dashboard = QuantLabDashboardService(CornerWatchRepository())
    analytics = dashboard.render_html("view=analytics&lab=corner")

    assert "UNDER mid-lines 7.5–10.5" in analytics
    assert "bucket_corner_calibration_watch_bucket=" in analytics
    assert "bucket_line_bucket=8.5" in analytics

    drilldown = dashboard.render_html(
        "view=analytics&lab=corner"
        "&bucket=1"
        "&bucket_corner_calibration_watch_bucket=UNDER+mid-lines+7.5%E2%80%9310.5"
        "&bucket_selection=UNDER"
        "&bucket_line_bucket=8.5"
        "&bucket_model_probability_bucket=55%E2%80%9360%25"
        "&bucket_market_probability_bucket=50%E2%80%9355%25"
        "&bucket_entry_odds_bucket=1.81%E2%80%932.00"
    )

    assert "1 exact settled picks" in drilldown
    assert "Corner Watch In" in drilldown
    assert "Corner Watch Out" not in drilldown


def test_cardlab_gets_raw_statistics_analytics_surface() -> None:
    class CardAnalyticsRepository(StubRepository):
        def list_all_bets(self, lab: str):
            assert lab == "CARD"
            row = corner_pick(outcome="WIN", suffix="card-analytics")
            row.update(
                {
                    "lab": "CARD",
                    "fixture_id": "api-football:card-analytics",
                    "provider_bet_id": 80,
                    "provider_bet_name": "Cards Over/Under",
                    "market_key": "TOTAL_CARDS",
                    "selection": "OVER",
                    "line": 4.5,
                    "policy_version": "CARDLAB_RAW_STATS_POLICY_V7_REFEREE_WEB",
                    "model_name": "CardLab raw-stat consensus",
                    "model_version": "CARDLAB_RAW_STATS_V1",
                    "odds": 1.85,
                    "stake_minor": 10_000,
                    "pnl_minor": 8_500,
                    "decision_reason": "RAW_STAT_CONSENSUS_PICK",
                    "card_feature_payload": {
                        "raw_features": {
                            "home_history_n": 12,
                            "away_history_n": 11,
                            "raw_anchor_count": 6,
                            "raw_consensus_cards": 5.4,
                            "referee_l10_cards": 5.8,
                            "referee_l10_fouls": 25.0,
                            "web_referee_league_key": "england_premier_league",
                            "web_referee_matches": 24,
                            "web_referee_cards_per_match": 5.6,
                            "web_referee_yellows_per_match": 5.2,
                            "web_referee_reds_per_match": 0.17,
                            "web_referee_home_away_bias": 0.25,
                            "combined_team_cards_for_l10": 5.2,
                            "combined_fouls_committed_l10": 28.0,
                            "matchup_expected_cards_l10": 5.3,
                            "matchup_expected_fouls_l10": 27.5,
                            "home_l10_cards_per_foul": 0.21,
                            "away_l10_cards_per_foul": 0.20,
                            "away_l10_fouls_suffered": 13.0,
                            "home_l10_fouls_suffered": 12.5,
                            "aggression_foul_draw_interaction": 2.6,
                            "h2h_total_cards_l5": 5.1,
                            "h2h_n": 3,
                            "league_total_cards": 4.7,
                            "referee_vs_league_cards_delta": 1.1,
                            "referee_vs_teams_cards_delta": 0.6,
                            "home_cards_for_league_percentile": 0.75,
                            "away_cards_for_league_percentile": 0.70,
                            "home_fouls_league_percentile": 0.65,
                            "away_fouls_league_percentile": 0.72,
                            "stage_of_season": 0.80,
                            "match_importance": 0.82,
                            "table_pressure": 0.78,
                            "must_win_proxy": 0.70,
                            "rank_gap": 2,
                            "points_gap": 3,
                            "derby_rivalry_indicator": 1,
                            "cup_indicator": 0,
                            "late_season_indicator": 1,
                            "similar_strength_indicator": 1,
                            "market_favorite_fair_probability": 0.52,
                            "market_one_x_two_balance": 0.92,
                            "market_goals_over_2_5_fair_probability": 0.58,
                            "market_btts_yes_fair_probability": 0.56,
                            "market_favorite_handicap_line": -0.5,
                            "expected_possession_imbalance": 6.0,
                            "home_l5_cards_for": 3.0,
                            "home_l10_cards_for": 2.7,
                            "away_l5_cards_for": 2.8,
                            "away_l10_cards_for": 2.5,
                            "home_venue_l5_cards_for": 3.1,
                            "away_venue_l5_cards_for": 2.9,
                            "home_l5_fouls_committed": 14.0,
                            "home_l10_fouls_committed": 13.0,
                            "away_l5_fouls_committed": 15.0,
                            "away_l10_fouls_committed": 14.0,
                        }
                    },
                    "decision_details": {
                        "raw_signal": {
                            "consensus_cards": 5.4,
                            "line_gap": 0.9,
                            "anchor_count": 6,
                            "directional_support": 0.83,
                            "observed_hit_rate": 0.72,
                        }
                    },
                }
            )
            return (row,)

    html = QuantLabDashboardService(CardAnalyticsRepository()).render_html(
        "view=analytics&lab=card"
    )

    assert "CardLab Analytics" in html
    assert "Watchlist · ROI discovery" in html
    assert "RAW consensus × line × support" in html
    assert "Referee × team discipline × price" in html
    assert "Referee × fouls × matchup" in html
    assert "Discipline × foul-drawing interaction" in html
    assert "Importance × derby/cup × competitiveness" in html
    assert "CardLab raw-stat bucket universe" in html
    assert "CardLab cross-buckets" in html
    assert "Web referee cards / match" in html
    assert "Web referee 10+ match coverage" in html
    assert "Referee cards L10" in html
    assert "Home cards-for L10" in html
    assert "Matchup expected cards" in html
    assert "1X2 balance" in html
    assert "Feature missingness" in html
    assert "Raw policy regime" in html
    assert "Expected value" not in html
    assert "Avg EV" not in html
    assert "Calibration" not in html
