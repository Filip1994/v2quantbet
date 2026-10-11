"""Bounded QuantLab analytics DOM with complete, stable drilldown pagination."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from h2h.quantlab.dashboard_views import (
    _ANALYTICS_PAGE_SIZE,
    _analytics_page,
    _bucket_detail_rows,
    _bucket_pick_table,
    _cohort_table,
    _sortable_th,
)


NOW = datetime(2026, 10, 11, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("requested", "expected"),
    [("1", 1), ("2", 2), ("-100", 1), ("0", 1), ("banana", 1), ("99999999", 3)],
)
def test_page_number_is_bounded(requested: str, expected: int) -> None:
    rows = tuple({"n": i} for i in range(2 * _ANALYTICS_PAGE_SIZE + 7))
    selected, page, pages = _analytics_page(
        rows, params={"league_page": [requested]}, table_key="league"
    )
    assert page == expected
    assert pages == 3
    assert len(selected) == (7 if expected == 3 else _ANALYTICS_PAGE_SIZE)


def _cohort(i: int) -> dict:
    return {
        "competition_name": f"League-{i:03}",
        "n": i + 1,
        "wins": 1,
        "losses": i,
        "voids": 0,
        "win_rate_pct": 1.0,
        "expected_win_rate_pct": 1.0,
        "calibration_gap_pp": 0.0,
        "roi_pct": float(i),
        "pnl_minor": 100,
        "avg_odds": 1.8,
        "brier_score": 0.1,
        "log_loss": 0.2,
        "avg_clv_pct": 0.0,
        "clv_n": 1,
        "closing_coverage_pct": 1.0,
        "max_drawdown_minor": 0,
        "avg_edge_pct": 0.01,
        "avg_ev_pct": 0.02,
        "sample_band": "MONITOR",
    }


def test_cohort_html_pages_preserve_full_roi_and_unique_drilldown_links() -> None:
    rows = tuple(_cohort(i) for i in range(95))
    all_groups: list[str] = []
    for page in range(1, 4):
        params = {"lab": ["goal"], "league_page": [str(page)]}
        html = _cohort_table(
            "Competition",
            rows,
            ("competition_name",),
            lab_key="goal",
            table_key="league",
            params=params,
            currency="RSD",
        )
        assert html.count("<tr>") == (41 if page < 3 else 16)
        assert "95 total rows" in html
        assert f"Page {page} of 3" in html
        assert 'href="/quantlab?' in html
        for i in range(95):
            label = f"League-{i:03}"
            if label in html:
                all_groups.append(label)
        if page == 1:
            assert "league_page=2" in html
            assert "League-094" in html
            assert "League-000" not in html
        if page == 3:
            assert "league_page=2" in html
            assert "League-000" in html

    assert len(all_groups) == 95
    assert set(all_groups) == {f"League-{i:03}" for i in range(95)}


def _pick(i: int) -> dict:
    return {
        "fixture_id": f"api-football:{i + 1000}",
        "goal_pick_id": f"pick-{i:03}",
        "home_team": f"Home-{i:03}",
        "away_team": "Away",
        "competition_name": "Premier League",
        "market_key": "OU_25",
        "selection": "OVER",
        "bookmaker_name": "1xBet",
        "odds": 1.8,
        "model_probability": 0.6,
        "edge": 0.1,
        "expected_value": 0.08,
        "outcome": "WIN",
        "pnl_minor": 100,
        "kickoff_at": NOW,
        "settled_at": NOW + timedelta(minutes=i),
    }


def test_exact_bucket_pick_drilldown_remains_complete_over_three_pages() -> None:
    rows = tuple(_pick(i) for i in range(95))
    all_matches: list[str] = []
    for page in range(1, 4):
        params = {
            "lab": ["goal"],
            "bucket": ["1"],
            "bucket_market_key": ["OU_25"],
            "bucket_picks_page": [str(page)],
            "bucket_picks_sort": ["settled_at"],
            "bucket_picks_dir": ["asc"],
        }
        selected, _ = _bucket_detail_rows(rows, params) or ((), "")
        assert len(selected) == 95  # Page control is NEVER a bucket filter.
        html = _bucket_pick_table(rows, params=params, lab_key="goal", currency="RSD")
        assert html.count("<tr>") == (41 if page < 3 else 16)
        assert "95 exact settled picks" in html
        assert f"Page {page} of 3" in html
        assert "bucket_market_key=OU_25" in html
        assert "bucket_picks_page=" in html
        for i in range(95):
            label = f"Home-{i:03}"
            if label in html:
                all_matches.append(label)
        if page == 3:
            assert "Home-094" in html
            assert "Home-000" not in html

    assert len(all_matches) == 95
    assert set(all_matches) == {f"Home-{i:03}" for i in range(95)}


def test_sort_header_resets_only_its_own_table_page() -> None:
    html = _sortable_th(
        "ROI", "roi_pct",
        table_key="league",
        params={
            "lab": ["goal"], "league_page": ["3"],
            "bucket_picks_page": ["4"],
        },
        anchor="analytics-league",
        active_key="n",
        active_dir="desc",
        first_dir="desc",
    )
    assert "league_page=1" in html
    assert "bucket_picks_page=4" in html
    assert "league_sort=roi_pct" in html
