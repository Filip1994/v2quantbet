from __future__ import annotations

import base64
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from h2h import entrypoint
from h2h.api.research_dashboard import (
    ResearchDashboardHTTPService,
    ResearchDashboardService,
)


NOW = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)


def _signal(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "signal_id": "research-signal-v1:abc",
        "detected_at": NOW,
        "capture_source": "LIVE",
        "fixture_id": "api-football:123",
        "provider_fixture_id": "123",
        "league_id": 140,
        "season": 2026,
        "home_team": "Home <script>",
        "away_team": "Away & Co",
        "competition_name": "Research League",
        "country": "Test",
        "kickoff_at": NOW,
        "provider_status": "FT",
        "market": "OU_25",
        "selected_selection": "OVER",
        "bookmaker_key": "bet365",
        "selected_odd": 2.10,
        "companion_odd": 1.80,
        "model_probability": 0.60,
        "selected_devig_probability": 0.48,
        "edge": 0.12,
        "expected_value": 0.26,
        "quote_observed_at": NOW,
        "source": "api-football",
        "model_version_id": "dc-v1",
        "monitoring_state": "CLOSED_FOR_ODDS",
        "monitoring_updated_at": NOW,
        "closing_outcome": "CAPTURED",
        "closing_odd": 2.00,
        "closing_observed_at": NOW,
        "latest_same_book_odd": 2.00,
        "latest_same_book_observed_at": NOW,
        "result_phase": "COMPLETE",
        "candidate_confirmation_count": 2,
        "result_classification": "PLAYED_SETTLEABLE",
        "result_provider_status": "FT",
        "regulation_home_goals": 2,
        "regulation_away_goals": 1,
        "first_acquired_at": NOW,
    }
    row.update(changes)
    return row


class StaticResearchDashboard(ResearchDashboardService):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self._fixed_stake_minor = 30_000

    def snapshot(self) -> dict[str, object]:
        rows = [dict(row) for row in self._rows]
        for row in rows:
            row["counterfactual_outcome"] = self._outcome(row)
            row["counterfactual_pnl_minor"] = self._pnl(row)
            row["clv_ppm"] = self._clv(row)
        return {"generated_at": NOW, "signals": rows}


def test_research_result_is_not_counted_before_stable_finality() -> None:
    row = _signal(result_phase="STABILIZING")

    assert ResearchDashboardService._outcome(row) is None


def test_research_dashboard_computes_counterfactual_result_pnl_and_clv() -> None:
    html = StaticResearchDashboard([_signal()]).render_html()

    assert "Home &lt;script&gt; – Away &amp; Co" in html
    assert "<script>" not in html
    assert "OU_25 OVER" in html
    assert "Signal odds" in html
    assert "Signal→close CLV" in html
    assert "60.00%" in html
    assert "26.00%" in html
    assert "+5.00%" in html
    assert ">WIN</strong>" in html
    assert "330.00 RSD" in html
    assert "fixture 123" in html
    assert "Research League" in html


def test_research_http_is_get_only_and_authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QUANTBET_RESEARCH_PUBLIC", raising=False)
    monkeypatch.setenv("QUANTBET_RESEARCH_USER", "research")
    monkeypatch.setenv("QUANTBET_RESEARCH_PASSWORD", "secret")
    service = ResearchDashboardHTTPService(
        StaticResearchDashboard([]), host="127.0.0.1", port=0
    )
    service.start()
    try:
        url = f"http://127.0.0.1:{service.port}/"
        with pytest.raises(HTTPError) as unauthorized:
            urlopen(url)
        assert unauthorized.value.code == 401

        token = base64.b64encode(b"research:secret").decode()
        with urlopen(Request(url, headers={"Authorization": f"Basic {token}"})) as response:
            assert response.status == 200
            assert response.headers["Content-Security-Policy"]

        with pytest.raises(HTTPError) as post:
            urlopen(
                Request(
                    f"http://127.0.0.1:{service.port}/api/picks/x/operator-state",
                    method="POST",
                    data=b"x",
                    headers={"Authorization": f"Basic {token}"},
                )
            )
        assert post.value.code == 404
    finally:
        service.close()


def test_root_entrypoint_dispatches_research_without_composing_worker(
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
        "load_production_settings",
        lambda: pytest.fail("worker settings must not load for research dashboard"),
    )

    entrypoint.main()

    assert calls == ["research"]
