from datetime import UTC, datetime, timedelta

from h2h.api.research_dashboard import (
    ResearchDashboardHTTPService,
    ResearchDashboardService,
    counterfactual_outcome,
    counterfactual_pnl_minor,
    research_clv_ppm,
)


NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


def signal_row():
    return {
        "research_signal_id": "research-signal-v1:" + "a" * 64,
        "evaluation_id": "value-evaluation-v1:" + "a" * 64,
        "fixture_id": "api-football:123",
        "provider_fixture_id": "123",
        "league_id": 39,
        "season": 2026,
        "stage": "PRELIMINARY",
        "block_reason": "MAX_OPEN_EXPOSURE_EXCEEDED",
        "first_blocked_at": NOW,
        "last_blocked_at": NOW,
        "blocked_count": 2,
        "first_open_exposure_minor": 300_000,
        "last_open_exposure_minor": 300_000,
        "exposure_cap_minor": 300_000,
        "qualified_at": NOW,
        "production_pick_id": None,
        "disposition": "BLOCKED_EXPOSURE",
        "home_team": "Home",
        "away_team": "Away",
        "competition_name": "Research League",
        "country": "Test",
        "kickoff_at": NOW + timedelta(hours=2),
        "fixture_status": "NS",
        "market": "BTTS",
        "selection": "YES",
        "bookmaker": "Bet365",
        "model_version_id": "dcm-json-v1:" + "1" * 64,
        "prediction_method_version": "DIXON_COLES_V1",
        "devig_method_version": "PROPORTIONAL_TWO_WAY_V1",
        "policy_config_fingerprint": "pick-policy-config-v1:" + "2" * 64,
        "eligibility_policy_version": "ELIGIBILITY_V1",
        "risk_policy_version": "RISK_V1",
        "staking_policy_version": "FIXED_STAKE_V1",
        "bookmaker_policy_version": "SERBIA_ALLOWLIST_V1",
        "model_probability": 0.62,
        "market_fair_probability": 0.48,
        "odds": 2.20,
        "edge": 0.14,
        "expected_value": 0.364,
        "quote_observed_at": NOW - timedelta(seconds=120),
        "quote_captured_at": NOW - timedelta(seconds=115),
        "source": "api-football",
        "closing_odds": 2.00,
        "closing_observed_at": NOW + timedelta(hours=1),
        "closing_captured_at": NOW + timedelta(hours=1, seconds=5),
        "result_phase": "COMPLETE",
        "result_classification": "PLAYED_SETTLEABLE",
        "result_provider_status": "FT",
        "regulation_home_goals": 1,
        "regulation_away_goals": 1,
    }


class Repository:
    def list_signals(self, *, limit):
        assert limit == 5000
        return (signal_row(),)


class DuplicateFixtureRepository:
    def list_signals(self, *, limit):
        assert limit == 5000
        weaker = signal_row()
        weaker["evaluation_id"] = "value-evaluation-v1:" + "b" * 64
        weaker["research_signal_id"] = "research-signal-v1:" + "b" * 64
        weaker["market"] = "OU_25"
        weaker["selection"] = "OVER"
        weaker["expected_value"] = 0.20
        stronger = signal_row()
        stronger["expected_value"] = 0.40
        return (weaker, stronger)


class SegmentedRepository:
    def list_signals(self, *, limit):
        assert limit == 5000

        win = signal_row()

        pending = signal_row()
        pending["research_signal_id"] = "research-signal-v1:" + "c" * 64
        pending["evaluation_id"] = "value-evaluation-v1:" + "c" * 64
        pending["fixture_id"] = "api-football:124"
        pending["provider_fixture_id"] = "124"
        pending["home_team"] = "Pending Home"
        pending["away_team"] = "Pending Away"
        pending["kickoff_at"] = NOW + timedelta(hours=5)
        pending["result_phase"] = "WAITING"
        pending["result_classification"] = None
        pending["result_provider_status"] = "NS"
        pending["regulation_home_goals"] = None
        pending["regulation_away_goals"] = None
        pending["closing_odds"] = None
        pending["closing_observed_at"] = None
        pending["closing_captured_at"] = None
        pending["block_reason"] = None
        pending["first_blocked_at"] = None
        pending["last_blocked_at"] = None
        pending["blocked_count"] = None
        pending["first_open_exposure_minor"] = None
        pending["last_open_exposure_minor"] = None
        pending["exposure_cap_minor"] = None
        pending["production_pick_id"] = "registered-pick-v1:" + "c" * 64
        pending["disposition"] = "PLAYED"

        awaiting = signal_row()
        awaiting["research_signal_id"] = "research-signal-v1:" + "e" * 64
        awaiting["evaluation_id"] = "value-evaluation-v1:" + "e" * 64
        awaiting["fixture_id"] = "api-football:126"
        awaiting["provider_fixture_id"] = "126"
        awaiting["home_team"] = "Awaiting Home"
        awaiting["away_team"] = "Awaiting Away"
        awaiting["kickoff_at"] = NOW - timedelta(hours=4)
        awaiting["result_phase"] = "POLLING"
        awaiting["result_classification"] = "NON_TERMINAL"
        awaiting["result_provider_status"] = "NS"
        awaiting["regulation_home_goals"] = None
        awaiting["regulation_away_goals"] = None
        awaiting["closing_odds"] = None
        awaiting["closing_observed_at"] = None
        awaiting["closing_captured_at"] = None

        loss = signal_row()
        loss["research_signal_id"] = "research-signal-v1:" + "d" * 64
        loss["evaluation_id"] = "value-evaluation-v1:" + "d" * 64
        loss["fixture_id"] = "api-football:125"
        loss["provider_fixture_id"] = "125"
        loss["home_team"] = "Loss Home"
        loss["away_team"] = "Loss Away"
        loss["kickoff_at"] = NOW - timedelta(hours=3)
        loss["regulation_home_goals"] = 1
        loss["regulation_away_goals"] = 0
        loss["block_reason"] = None
        loss["first_blocked_at"] = None
        loss["last_blocked_at"] = None
        loss["blocked_count"] = None
        loss["first_open_exposure_minor"] = None
        loss["last_open_exposure_minor"] = None
        loss["exposure_cap_minor"] = None
        loss["production_pick_id"] = "registered-pick-v1:" + "d" * 64
        loss["disposition"] = "SKIPPED"

        return (pending, awaiting, win, loss)


class LeagueVersionRepository:
    def list_signals(self, *, limit):
        assert limit == 5000

        first = signal_row()

        retrain = signal_row()
        retrain["research_signal_id"] = "research-signal-v1:" + "f" * 64
        retrain["evaluation_id"] = "value-evaluation-v1:" + "f" * 64
        retrain["fixture_id"] = "api-football:127"
        retrain["provider_fixture_id"] = "127"
        retrain["home_team"] = "Retrain Home"
        retrain["away_team"] = "Retrain Away"
        retrain["kickoff_at"] = NOW + timedelta(hours=3)
        retrain["model_version_id"] = "dcm-json-v1:" + "3" * 64
        retrain["regulation_home_goals"] = 1
        retrain["regulation_away_goals"] = 0

        other_league = signal_row()
        other_league["research_signal_id"] = "research-signal-v1:" + "9" * 64
        other_league["evaluation_id"] = "value-evaluation-v1:" + "9" * 64
        other_league["fixture_id"] = "api-football:128"
        other_league["provider_fixture_id"] = "128"
        other_league["league_id"] = 40
        other_league["competition_name"] = "Other League"
        other_league["home_team"] = "Other Home"
        other_league["away_team"] = "Other Away"
        other_league["kickoff_at"] = NOW + timedelta(hours=4)
        other_league["model_version_id"] = "dcm-json-v1:" + "4" * 64

        return (first, retrain, other_league)


def test_counterfactual_result_pnl_and_clv_are_research_only_math() -> None:
    row = signal_row()

    assert counterfactual_outcome(row) == "WIN"
    assert counterfactual_pnl_minor(row, 30_000) == 36_000
    assert research_clv_ppm(row) == 100_000


def test_research_dashboard_maps_match_and_supports_bucket_filters() -> None:
    dashboard = ResearchDashboardService(Repository())

    signals = dashboard.signals(
        {
            "p_min": ["60"],
            "p_max": ["65"],
            "ev_min": ["30"],
            "odds_min": ["2.0"],
            "market": ["BTTS"],
            "league": ["research"],
            "result": ["WIN"],
            "disposition": ["BLOCKED_EXPOSURE"],
            "p_bucket": ["60–65%"],
            "ev_bucket": ["30%+"],
            "odds_bucket": ["2.01–2.50"],
        }
    )
    assert len(signals) == 1
    assert signals[0]["probability_bucket"] == "60–65%"
    assert signals[0]["ev_bucket"] == "30%+"
    assert signals[0]["freshness"] == "FRESH"

    html = dashboard.render_html("tab=history&p_min=60&p_max=65")
    assert "Home – Away" in html
    assert "Research League" in html
    assert "fixture 123" in html
    assert "36.4%" in html
    assert "+10.00%" in html


def test_research_dashboard_projects_one_canonical_pick_per_fixture() -> None:
    rows = ResearchDashboardService(DuplicateFixtureRepository()).signals({})

    assert len(rows) == 1
    assert rows[0]["market"] == "BTTS"
    assert rows[0]["evaluation_id"] == "value-evaluation-v1:" + "a" * 64


def test_research_dashboard_separates_active_and_history_tabs() -> None:
    dashboard = ResearchDashboardService(SegmentedRepository(), clock=lambda: NOW)

    active_html = dashboard.render_html("tab=active")
    assert "Active research board" in active_html
    assert "Pending Home – Pending Away" in active_html
    assert "Awaiting Home – Awaiting Away" not in active_html
    assert "Home – Away" not in active_html
    assert "Loss Home – Loss Away" not in active_html
    assert 'class="active" href=' in active_html
    assert 'name="result"' not in active_html
    assert "PLAYED" in active_html
    assert "production candidate" in active_html
    assert 'class="bookmaker-mark bookmaker-bet365"' in active_html
    assert "System status" in active_html
    assert "Database" in active_html
    assert "Engine" in active_html
    assert "Models" in active_html
    assert "Odds" in active_html
    assert "Results" in active_html
    assert "Research" in active_html
    assert "health-unknown" in active_html

    awaiting_html = dashboard.render_html("tab=awaiting")
    assert "Awaiting result" in awaiting_html
    assert "Awaiting Home – Awaiting Away" in awaiting_html
    assert "Pending Home – Pending Away" not in awaiting_html
    assert "POLLING" in awaiting_html
    assert "NS" in awaiting_html
    assert "History" in awaiting_html

    history_html = dashboard.render_html("tab=history")
    assert "Settled research history" in history_html
    assert "Pending Home – Pending Away" not in history_html
    assert "Awaiting Home – Awaiting Away" not in history_html
    assert "Home – Away" in history_html
    assert "Loss Home – Loss Away" in history_html
    assert 'class="badge result-win"' in history_html
    assert 'class="badge result-loss"' in history_html
    assert 'class="row-win"' in history_html
    assert 'class="row-loss"' in history_html
    assert 'class="result-panel result-panel-win"' in history_html
    assert 'class="result-panel result-panel-loss"' in history_html
    assert '<div class="score">1 : 1</div>' in history_html
    assert '<div class="score">1 : 0</div>' in history_html
    assert "<th>Match</th><th>Result</th><th>Pick</th>" in history_html
    assert 'name="result"' in history_html
    assert "BLOCKED EXPOSURE" in history_html
    assert "SKIPPED" in history_html
    assert 'name="disposition"' in history_html
    assert 'name="p_bucket"' in history_html
    assert 'name="ev_bucket"' in history_html
    assert 'name="odds_bucket"' in history_html
    assert 'class="bookmaker-mark bookmaker-bet365"' in history_html


def test_research_history_result_filter_and_sportsbook_palette() -> None:
    dashboard = ResearchDashboardService(SegmentedRepository(), clock=lambda: NOW)

    html = dashboard.render_html("tab=history&result=LOSS")

    assert "Loss Home – Loss Away" in html
    assert "Home – Away" not in html
    assert "--bg:#111315" in html
    assert "--panel:#181b1f" in html
    assert "--win:#69c98f" in html
    assert "--loss:#e06f78" in html
    assert "QUANT" in html
    assert "BET" in html
    assert 'class="sportsbook-logo"' in html
    assert "Research Board" in html
    assert "Research universe" in html


def test_research_dashboard_supports_exact_analytics_cohort_filters() -> None:
    dashboard = ResearchDashboardService(Repository())
    row = signal_row()
    week_year, week_number, _ = row["kickoff_at"].isocalendar()
    week = f"{week_year}-W{week_number:02d}"

    filters = {
        "market": ["BTTS"],
        "selection": ["YES"],
        "bookmaker": ["bet365"],
        "p_bucket": ["60–65%"],
        "fair_bucket": ["45–50%"],
        "ev_bucket": ["30%+"],
        "odds_bucket": ["2.01–2.50"],
        "model_version": [row["model_version_id"]],
        "policy_config": [row["policy_config_fingerprint"]],
        "prediction_method": [row["prediction_method_version"]],
        "devig_method": [row["devig_method_version"]],
        "freshness": ["FRESH"],
        "diagnostic": ["OTHER_EXTREME"],
        "week": [week],
    }

    assert len(dashboard.signals(filters)) == 1
    assert dashboard.signals({**filters, "selection": ["NO"]}) == ()
    assert dashboard.signals({**filters, "fair_bucket": ["50–55%"]}) == ()
    assert dashboard.signals({**filters, "diagnostic": ["LOW_SCORING_EXTREME"]}) == ()


def test_research_dashboard_can_filter_by_production_route() -> None:
    dashboard = ResearchDashboardService(SegmentedRepository(), clock=lambda: NOW)

    played = dashboard.signals({"disposition": ["PLAYED"]})
    skipped = dashboard.signals({"disposition": ["SKIPPED"]})
    blocked = dashboard.signals({"disposition": ["BLOCKED_EXPOSURE"]})

    assert [row["fixture_id"] for row in played] == ["api-football:124"]
    assert [row["fixture_id"] for row in skipped] == ["api-football:125"]
    assert [row["fixture_id"] for row in blocked] == [
        "api-football:126",
        "api-football:123",
    ]


def test_clv_is_unavailable_without_a_later_stored_quote() -> None:
    row = signal_row()
    row["closing_observed_at"] = row["quote_observed_at"]

    assert research_clv_ppm(row) is None


def test_research_dashboard_can_be_explicitly_public(monkeypatch) -> None:
    monkeypatch.setenv("QUANTBET_RESEARCH_PUBLIC", "true")
    monkeypatch.delenv("QUANTBET_RESEARCH_PASSWORD", raising=False)

    assert ResearchDashboardHTTPService._authorize(object()) is True


def test_research_dashboard_exposes_exact_diagnostic_rows() -> None:
    dashboard = ResearchDashboardService(Repository())

    payload = dashboard.diagnostic_details("OTHER_EXTREME")

    assert payload["contract_version"] == "RESEARCH_DIAGNOSTIC_DRILLDOWN_V1"
    assert payload["bucket"] == "OTHER_EXTREME"
    assert payload["count"] == 1
    assert payload["wins"] == 1
    assert payload["losses"] == 0
    assert payload["rows"][0]["fixture_id"] == "api-football:123"
    assert payload["rows"][0]["home_team"] == "Home"
    assert payload["rows"][0]["away_team"] == "Away"
    assert payload["rows"][0]["market"] == "BTTS"
    assert payload["rows"][0]["selection"] == "YES"
    assert payload["rows"][0]["score"] == {"home": 1, "away": 1}
    assert payload["rows"][0]["clv_pct"] == 10.0


def test_research_dashboard_exposes_continuous_analytics_v1() -> None:
    dashboard = ResearchDashboardService(Repository())

    signal = dashboard.signals({})[0]
    assert signal["market_fair_probability_bucket"] == "45–50%"

    snapshot = dashboard.analytics_snapshot()
    assert snapshot["contract_version"] == "RESEARCH_ANALYTICS_V2"
    assert snapshot["windows"]["lifetime"]["n"] == 1
    assert snapshot["cohorts"]["market_selection"][0]["market"] == "BTTS"
    assert snapshot["cohorts"]["league_season"][0]["league_id"] == "39"
    assert snapshot["cohorts"]["league_season"][0]["season"] == "2026"
    assert snapshot["version_summary"]["model_version_count"] == 1
    assert snapshot["version_summary"]["policy_config_count"] == 1
    assert snapshot["cohorts"]["model_policy"][0]["model_version_id"].startswith(
        "dcm-json-v1:"
    )

    html = dashboard.render_analytics_html()
    assert "Research Analytics V2" in html
    assert "Core performance" in html
    assert "Calibration &amp; price" in html
    assert "Audit" in html
    assert "Production filter cube" in html
    assert "Low-scoring diagnostic" in html
    assert "Leagues · all retrains combined" in html
    assert "Model versions · individual retrains" not in html
    assert "/research/analytics/league?league_id=39&amp;season=2026" in html
    assert "/research?tab=history&amp;market=BTTS&amp;selection=YES" in html
    assert "/research?tab=history&amp;diagnostic=OTHER_EXTREME" in html
    assert "/research?tab=history&amp;p_bucket=60%E2%80%9365%25" in html
    assert "/research?tab=history&amp;fair_bucket=45%E2%80%9350%25" in html
    assert "/research?tab=history&amp;ev_bucket=30%25%2B" in html
    assert "/research?tab=history&amp;odds_bucket=2.01%E2%80%932.50" in html
    assert "/research?tab=history&amp;policy_config=pick-policy-config-v1%3A" in html
    assert (
        "/research/analytics/model?model_version_id=dcm-json-v1%3A"
        in html
    )


def test_research_model_version_drilldown_exposes_constituent_picks() -> None:
    dashboard = ResearchDashboardService(Repository())
    model_version_id = signal_row()["model_version_id"]

    payload = dashboard.model_version_details(model_version_id)

    assert payload["contract_version"] == "RESEARCH_MODEL_VERSION_DRILLDOWN_V1"
    assert payload["model_version_id"] == model_version_id
    assert payload["summary"]["n"] == 1
    assert payload["summary"]["wins"] == 1
    assert payload["summary"]["roi_pct"] == 120.0
    assert payload["rows"][0]["fixture_id"] == "api-football:123"
    assert payload["rows"][0]["home_team"] == "Home"
    assert payload["rows"][0]["away_team"] == "Away"
    assert payload["rows"][0]["market"] == "BTTS"
    assert payload["rows"][0]["selection"] == "YES"
    assert payload["rows"][0]["odds"] == 2.2
    assert payload["rows"][0]["outcome"] == "WIN"
    assert payload["rows"][0]["pnl_minor"] == 36_000
    assert payload["rows"][0]["clv_pct"] == 10.0
    assert payload["rows"][0]["policy_config_fingerprint"].startswith(
        "pick-policy-config-v1:"
    )

    html = dashboard.render_model_version_html(model_version_id)
    assert "Model version picks" in html
    assert "Home – Away" in html
    assert "BTTS YES" in html
    assert "2.20" in html
    assert "+120.00%" in html
    assert "pick-policy-config-v1:" in html
    assert "/research/analytics/model.json?model_version_id=" in html



def test_research_league_drilldown_combines_retrains_and_preserves_model_audit() -> None:
    dashboard = ResearchDashboardService(LeagueVersionRepository())

    payload = dashboard.league_details(39, 2026)

    assert payload["contract_version"] == "RESEARCH_LEAGUE_DRILLDOWN_V1"
    assert payload["league"]["league_id"] == 39
    assert payload["league"]["season"] == 2026
    assert payload["league"]["competition_name"] == "Research League"
    assert payload["summary"]["n"] == 2
    assert payload["summary"]["wins"] == 1
    assert payload["summary"]["losses"] == 1
    assert payload["summary"]["roi_pct"] == 10.0
    assert payload["model_version_count"] == 2
    assert {row["model_version_id"] for row in payload["model_versions"]} == {
        "dcm-json-v1:" + "1" * 64,
        "dcm-json-v1:" + "3" * 64,
    }
    assert {row["provider_fixture_id"] for row in payload["rows"]} == {"123", "127"}
    assert all(row["league_id"] == 39 for row in payload["rows"])

    html = dashboard.render_league_html(39, 2026)

    assert "Research League · 2026" in html
    assert "all DC retrains combined" in html
    assert "Model versions · retrain history" in html
    assert "All settled picks · all retrains" in html
    assert "Home – Away" in html
    assert "Retrain Home – Retrain Away" in html
    assert "Other Home – Other Away" not in html
    assert "/research/analytics/model?model_version_id=" in html
    assert "/research/analytics/league.json?league_id=39&amp;season=2026" in html
