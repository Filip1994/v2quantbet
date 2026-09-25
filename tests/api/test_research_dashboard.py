from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from h2h import entrypoint
from h2h.api.research_dashboard import ResearchDashboardService


NOW = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)


def _row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "evaluation_id": "value-evaluation-v1:" + "1" * 64,
        "first_blocked_at": NOW,
        "last_blocked_at": NOW + timedelta(minutes=1),
        "block_count": 2,
        "first_open_exposure_minor": 300_000,
        "last_open_exposure_minor": 300_000,
        "max_open_exposure_minor": 300_000,
        "fixed_stake_minor": 30_000,
        "capture_origin": "LIVE",
        "fixture_id": "api-football:1577950",
        "provider_fixture_id": "1577950",
        "league_id": 39,
        "season": 2026,
        "home_team": "Home FC",
        "away_team": "Away United",
        "competition_name": "Research League",
        "country": "Testland",
        "kickoff_at": NOW + timedelta(hours=2),
        "provider_status": "NS",
        "market": "OU_25",
        "selection": "UNDER",
        "bookmaker_id": 8,
        "bookmaker_key": "bet365",
        "source": "api-football",
        "signal_odd": 2.0,
        "companion_odd": 1.8,
        "quote_observed_at": NOW - timedelta(minutes=2),
        "selected_captured_at": NOW - timedelta(minutes=2),
        "model_probability": 0.65,
        "market_fair_probability": 0.52,
        "edge": 0.13,
        "expected_value": 0.30,
        "model_version_id": "dc-v1",
        "prediction_method_version": "DIXON_COLES_MARKET_PROBABILITIES_V1",
        "observed_closing_odd": 1.8,
        "observed_closing_at": NOW + timedelta(hours=1, minutes=55),
        "result_phase": "COMPLETE",
        "result_provider_status": "FT",
        "regulation_home_goals": 1,
        "regulation_away_goals": 0,
        "result_classification": "PLAYED_SETTLEABLE",
        "eventually_registered": False,
    }
    row.update(changes)
    return row


class StaticResearchDashboard(ResearchDashboardService):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._static_rows = rows

    def rows(self, *, provider_fixture_id: str | None = None) -> list[dict[str, object]]:
        selected = [
            dict(row)
            for row in self._static_rows
            if provider_fixture_id is None
            or str(row["provider_fixture_id"]) == provider_fixture_id
        ]
        for row in selected:
            self._derive(row)
        return selected


def test_research_dashboard_maps_fixture_and_derives_clv_outcome_and_buckets() -> None:
    dashboard = StaticResearchDashboard([_row()])
    snapshot = dashboard.snapshot()
    row = snapshot["rows"][0]

    assert row["counterfactual_outcome"] == "WIN"
    assert row["counterfactual_units"] == pytest.approx(1.0)
    assert row["research_clv"] == pytest.approx((2.0 / 1.8) - 1.0)
    assert row["probability_bucket"] == "65–70%"
    assert row["ev_bucket"] == "30%+"

    html = dashboard.render_html()
    assert "1577950" in html
    assert "Home FC – Away United" in html
    assert "Research League" in html
    assert "65.00%" in html
    assert "fair 52.00%" in html
    assert "EV +30.00%" in html
    assert "+11.11%" in html
    assert "+1.00u" in html


def test_research_dashboard_fixture_filter_is_exact() -> None:
    dashboard = StaticResearchDashboard(
        [
            _row(provider_fixture_id="1577950"),
            _row(
                evaluation_id="value-evaluation-v1:" + "2" * 64,
                fixture_id="api-football:123",
                provider_fixture_id="123",
                home_team="Other",
            ),
        ]
    )

    snapshot = dashboard.snapshot(provider_fixture_id="1577950")

    assert snapshot["counts"]["signals"] == 1
    assert snapshot["rows"][0]["home_team"] == "Home FC"


def test_root_entrypoint_dispatches_research_dashboard_without_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("QUANTBET_PROCESS", "research-dashboard")
    monkeypatch.setattr(
        "h2h.research_dashboard_entrypoint.main",
        lambda: calls.append("research"),
    )
    monkeypatch.setattr(
        entrypoint,
        "build_production_application",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("worker composition must not run")
        ),
    )

    entrypoint.main()

    assert calls == ["research"]
