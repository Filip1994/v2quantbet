from datetime import UTC, datetime, timedelta
from decimal import Decimal

from h2h.api.research_dashboard import ResearchDashboardService


NOW = datetime(2026, 9, 25, 10, tzinfo=UTC)
KICKOFF = NOW + timedelta(hours=2)


def row(**changes):
    value = {
        "signal_id": "research-signal-v1:" + "a" * 64,
        "evaluation_id": "value-evaluation-v1:" + "a" * 64,
        "fixture_id": "api-football:123",
        "blocked_at": NOW,
        "blocked_stage": "PRELIMINARY_RISK",
        "capture_method": "LIVE_V1",
        "policy_fingerprint": "pick-policy-config-v1:" + "b" * 64,
        "provider_fixture_id": "123",
        "league_id": 140,
        "season": 2026,
        "fixture_observation_id": "fixture-observation-v1:" + "c" * 64,
        "home_team": "Home FC",
        "away_team": "Away United",
        "competition_name": "Research League",
        "country": "RS",
        "kickoff_at": KICKOFF,
        "provider_status": "NS",
        "bookmaker_id": 8,
        "bookmaker_key": "bet365",
        "market": "OU_25",
        "selection": "UNDER",
        "entry_odd": Decimal("2.10"),
        "market_fair_probability": 0.45,
        "model_probability": 0.60,
        "edge": 0.15,
        "expected_value": 0.26,
        "quote_observed_at": NOW,
        "quote_captured_at": NOW,
        "series_id": "series-1",
        "entry_snapshot_id": "snapshot-1",
        "source": "api-football",
        "model_version_id": "model-1",
        "closing_snapshot_id": "snapshot-close",
        "closing_odd": Decimal("2.00"),
        "closing_observed_at": KICKOFF - timedelta(minutes=5),
        "closing_captured_at": KICKOFF - timedelta(minutes=5),
        "result_observation_id": "result-1",
        "result_classification": "PLAYED_SETTLEABLE",
        "regulation_home_goals": 1,
        "regulation_away_goals": 0,
        "correction_required": False,
    }
    value.update(changes)
    return value


class Repository:
    def __init__(self, rows):
        self._rows = tuple(rows)

    def rows(self):
        return self._rows


def test_research_snapshot_maps_fixture_and_computes_shadow_result_and_clv() -> None:
    dashboard = ResearchDashboardService(
        Repository([row()]),  # type: ignore[arg-type]
        closing_max_age_seconds=900,
    )

    data = dashboard.snapshot(provider_fixture_id="123")
    signal = data["rows"][0]

    assert signal["home_team"] == "Home FC"
    assert signal["away_team"] == "Away United"
    assert signal["outcome"] == "WIN"
    assert signal["unit_pnl"] == Decimal("1.10")
    assert signal["clv_status"] == "AVAILABLE"
    assert signal["clv_ppm"] == 50_000
    assert data["summary"]["unique_fixtures"] == 1
    assert data["summary"]["unit_roi"] == Decimal("1.10")


def test_research_snapshot_refuses_stale_closing_as_clv() -> None:
    stale = row(
        closing_observed_at=KICKOFF - timedelta(minutes=16),
        closing_captured_at=KICKOFF - timedelta(minutes=16),
    )
    dashboard = ResearchDashboardService(
        Repository([stale]),  # type: ignore[arg-type]
        closing_max_age_seconds=900,
    )

    signal = dashboard.snapshot()["rows"][0]

    assert signal["closing_odd"] == Decimal("2.00")
    assert signal["closing_age_seconds"] == 960
    assert signal["clv_status"] == "STALE_CLOSING"
    assert signal["clv_ppm"] is None


def test_research_html_exposes_exact_match_mapping_without_bankroll_controls() -> None:
    dashboard = ResearchDashboardService(
        Repository([row()]),  # type: ignore[arg-type]
        closing_max_age_seconds=900,
    )

    html = dashboard.render_html()

    assert "123" in html
    assert "Home FC – Away United" in html
    assert "Research League" in html
    assert "Research CLV +5.00%" in html
    assert "bankroll reservations" in html
    assert "operator-state" not in html
