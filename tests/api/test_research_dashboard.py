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

        return (pending, win, loss)


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
    dashboard = ResearchDashboardService(SegmentedRepository())

    active_html = dashboard.render_html("tab=active")
    assert "Active research board" in active_html
    assert "Pending Home – Pending Away" in active_html
    assert "Home – Away" not in active_html
    assert "Loss Home – Loss Away" not in active_html
    assert 'class="active" href=' in active_html
    assert 'name="result"' not in active_html
    assert "PLAYED" in active_html
    assert "production candidate" in active_html

    history_html = dashboard.render_html("tab=history")
    assert "Settled research history" in history_html
    assert "Pending Home – Pending Away" not in history_html
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


def test_research_history_result_filter_and_sportsbook_palette() -> None:
    dashboard = ResearchDashboardService(SegmentedRepository())

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


def test_research_dashboard_can_filter_by_production_route() -> None:
    dashboard = ResearchDashboardService(SegmentedRepository())

    played = dashboard.signals({"disposition": ["PLAYED"]})
    skipped = dashboard.signals({"disposition": ["SKIPPED"]})
    blocked = dashboard.signals({"disposition": ["BLOCKED_EXPOSURE"]})

    assert [row["fixture_id"] for row in played] == ["api-football:124"]
    assert [row["fixture_id"] for row in skipped] == ["api-football:125"]
    assert [row["fixture_id"] for row in blocked] == ["api-football:123"]


def test_clv_is_unavailable_without_a_later_stored_quote() -> None:
    row = signal_row()
    row["closing_observed_at"] = row["quote_observed_at"]

    assert research_clv_ppm(row) is None


def test_research_dashboard_can_be_explicitly_public(monkeypatch) -> None:
    monkeypatch.setenv("QUANTBET_RESEARCH_PUBLIC", "true")
    monkeypatch.delenv("QUANTBET_RESEARCH_PASSWORD", raising=False)

    assert ResearchDashboardHTTPService._authorize(object()) is True
