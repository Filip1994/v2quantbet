from __future__ import annotations

from datetime import UTC, datetime

from h2h.api.research_dashboard import ResearchDashboardService


NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


class FakeRepository:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def signals(self, *, limit=2000, provider_fixture_id=None):
        self.filters.append(provider_fixture_id)
        if provider_fixture_id is None:
            return [dict(row) for row in self.rows]
        return [
            dict(row)
            for row in self.rows
            if row["provider_fixture_id"] == provider_fixture_id
        ]


def _row(**changes):
    row = {
        "evaluation_id": "value-evaluation-v1:abc",
        "blocked_at": NOW,
        "open_exposure_minor": 300000,
        "proposed_stake_minor": 30000,
        "max_open_exposure_minor": 300000,
        "capture_source": "LIVE_GATE",
        "provider_fixture_id": "1577950",
        "league_id": 1,
        "season": 2026,
        "home_team": "Home <Team>",
        "away_team": "Away & Team",
        "competition_name": "Research League",
        "country": "Test",
        "kickoff_at": NOW,
        "provider_status": "NS",
        "bookmaker_key": "bet365",
        "market": "OU_25",
        "selection": "UNDER",
        "entry_odd": 2.15,
        "market_fair_probability": 0.4372,
        "model_probability": 0.7128,
        "edge": 0.2756,
        "expected_value": 0.5325,
        "quote_observed_at": NOW,
        "source": "api-football",
        "selected_series_id": "series",
        "shadow_closing_snapshot_id": "close",
        "shadow_closing_odd": 1.95,
        "shadow_closing_observed_at": NOW,
        "shadow_closing_captured_at": NOW,
        "shadow_clv_ppm": 102564,
        "result_classification": "PLAYED_SETTLEABLE",
        "regulation_home_goals": 1,
        "regulation_away_goals": 0,
        "counterfactual_outcome": "WIN",
        "counterfactual_pnl_minor": 34500,
        "eventually_registered_pick_id": None,
        "eventually_registered_at": None,
        "eventually_registered_market": None,
        "eventually_registered_selection": None,
    }
    row.update(changes)
    return row


def test_research_dashboard_maps_fixture_and_keeps_shadow_metrics_separate():
    repo = FakeRepository([_row()])
    service = ResearchDashboardService(repo)

    html = service.render_html()

    assert "Home &lt;Team&gt; – Away &amp; Team" in html
    assert "ID 1577950" in html
    assert "71.28%" in html
    assert "EV 53.25%" in html
    assert "shadow close 1.95" in html
    assert "+10.26%" in html
    assert "WIN" in html
    assert "345.00 RSD" in html
    assert "Shadow ledger only" in html
    assert "<Team>" not in html


def test_snapshot_builds_probability_and_ev_research_buckets():
    repo = FakeRepository(
        [
            _row(),
            _row(
                evaluation_id="value-evaluation-v1:def",
                provider_fixture_id="123",
                model_probability=0.623,
                expected_value=0.154,
                counterfactual_outcome="LOSS",
                counterfactual_pnl_minor=-30000,
                shadow_clv_ppm=-10000,
            ),
        ]
    )
    data = ResearchDashboardService(repo).snapshot()

    assert data["counts"]["signals"] == 2
    assert data["counts"]["fixtures"] == 2
    assert data["counts"]["wins"] == 1
    assert data["counts"]["losses"] == 1
    assert {row["bucket"] for row in data["probability_buckets"]} == {"60-65%", "70-75%"}
    assert {row["bucket"] for row in data["ev_buckets"]} == {"15-20%", "30%+"}


def test_provider_fixture_filter_is_forwarded_to_repository():
    repo = FakeRepository([_row()])
    data = ResearchDashboardService(repo).snapshot(provider_fixture_id="1577950")

    assert repo.filters == ["1577950"]
    assert data["counts"]["signals"] == 1
    assert data["filter_provider_fixture_id"] == "1577950"
