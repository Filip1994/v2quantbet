from datetime import UTC, datetime

import pytest

from h2h.api.research_analytics import (
    build_research_analytics_snapshot,
    cohort_metrics,
    diagnostic_bucket,
    market_fair_probability_bucket,
)
from h2h.persistence.postgres_research_signals import PostgreSQLResearchSignalRepository


AS_OF = datetime(2026, 9, 27, 12, tzinfo=UTC)


def row(
    *,
    fixture: str,
    market: str,
    selection: str,
    outcome: str,
    model_probability: float,
    market_fair_probability: float,
    odds: float,
    edge: float,
    ev: float,
    pnl_minor: int,
    clv_ppm: int | None,
):
    return {
        "fixture_id": fixture,
        "market": market,
        "selection": selection,
        "outcome": outcome,
        "model_probability": model_probability,
        "market_fair_probability": market_fair_probability,
        "odds": odds,
        "edge": edge,
        "expected_value": ev,
        "pnl_minor": pnl_minor,
        "clv_ppm": clv_ppm,
        "probability_bucket": "65–70%",
        "market_fair_probability_bucket": market_fair_probability_bucket(
            market_fair_probability
        ),
        "ev_bucket": "30%+" if ev >= 0.30 else "10–15%",
        "odds_bucket": "1.81–2.00",
        "disposition": "BLOCKED_EXPOSURE",
        "bookmaker": "Bet365",
        "competition_name": "Research League",
        "freshness": "FRESH",
        "kickoff_at": AS_OF,
    }


def test_diagnostic_bucket_contract_is_reusable_for_drilldown() -> None:
    other_extreme = row(
        fixture="extreme",
        market="BTTS",
        selection="YES",
        outcome="WIN",
        model_probability=0.62,
        market_fair_probability=0.48,
        odds=2.20,
        edge=0.14,
        ev=0.30,
        pnl_minor=36_000,
        clv_ppm=100_000,
    )
    low_scoring_extreme = {
        **other_extreme,
        "market": "OU_25",
        "selection": "UNDER",
        "edge": 0.20,
        "expected_value": 0.10,
    }

    assert diagnostic_bucket(other_extreme) == "OTHER_EXTREME"
    assert diagnostic_bucket(low_scoring_extreme) == "LOW_SCORING_EXTREME"


def test_market_fair_probability_bucket_contract_is_stable() -> None:
    assert market_fair_probability_bucket(0.24) == "<25%"
    assert market_fair_probability_bucket(0.25) == "25–35%"
    assert market_fair_probability_bucket(0.45) == "45–50%"
    assert market_fair_probability_bucket(0.7499) == "65–75%"
    assert market_fair_probability_bucket(0.75) == "75%+"


def test_cohort_metrics_expose_roi_calibration_clv_and_uncertainty() -> None:
    rows = (
        row(
            fixture="1",
            market="BTTS",
            selection="NO",
            outcome="WIN",
            model_probability=0.70,
            market_fair_probability=0.45,
            odds=2.0,
            edge=0.25,
            ev=0.40,
            pnl_minor=30_000,
            clv_ppm=100_000,
        ),
        row(
            fixture="2",
            market="OU_25",
            selection="UNDER",
            outcome="LOSS",
            model_probability=0.60,
            market_fair_probability=0.40,
            odds=2.0,
            edge=0.20,
            ev=0.20,
            pnl_minor=-30_000,
            clv_ppm=-50_000,
        ),
        row(
            fixture="3",
            market="BTTS",
            selection="YES",
            outcome="WIN",
            model_probability=0.55,
            market_fair_probability=0.50,
            odds=2.0,
            edge=0.05,
            ev=0.10,
            pnl_minor=30_000,
            clv_ppm=0,
        ),
        row(
            fixture="4",
            market="BTTS",
            selection="YES",
            outcome="VOID",
            model_probability=0.50,
            market_fair_probability=0.50,
            odds=2.0,
            edge=0.05,
            ev=0.10,
            pnl_minor=0,
            clv_ppm=0,
        ),
    )

    metrics = cohort_metrics(rows, fixed_stake_minor=30_000)

    assert metrics["n"] == 4
    assert metrics["graded_n"] == 3
    assert metrics["wins"] == 2
    assert metrics["losses"] == 1
    assert metrics["voids"] == 1
    assert metrics["win_rate_pct"] == pytest.approx(66.6666667)
    assert metrics["expected_win_rate_pct"] == pytest.approx(61.6666667)
    assert metrics["calibration_gap_pp"] == pytest.approx(5.0)
    assert metrics["roi_pct"] == pytest.approx(33.3333333)
    assert metrics["avg_clv_pct"] == pytest.approx(1.25)
    assert metrics["median_clv_pct"] == pytest.approx(0.0)
    assert metrics["positive_clv_rate_pct"] == pytest.approx(25.0)
    assert metrics["win_rate_wilson_95_low_pct"] < metrics["win_rate_pct"]
    assert metrics["win_rate_wilson_95_high_pct"] > metrics["win_rate_pct"]
    assert metrics["sample_band"] == "SIGNAL_ONLY"


def test_snapshot_contains_continuous_windows_cohorts_and_low_scoring_diagnostic() -> None:
    rows = (
        row(
            fixture="1",
            market="BTTS",
            selection="NO",
            outcome="WIN",
            model_probability=0.70,
            market_fair_probability=0.45,
            odds=2.0,
            edge=0.25,
            ev=0.40,
            pnl_minor=30_000,
            clv_ppm=100_000,
        ),
        row(
            fixture="2",
            market="BTTS",
            selection="YES",
            outcome="LOSS",
            model_probability=0.55,
            market_fair_probability=0.50,
            odds=2.0,
            edge=0.05,
            ev=0.10,
            pnl_minor=-30_000,
            clv_ppm=-10_000,
        ),
        {
            **row(
                fixture="3",
                market="OU_25",
                selection="OVER",
                outcome="PENDING",
                model_probability=0.60,
                market_fair_probability=0.50,
                odds=2.0,
                edge=0.10,
                ev=0.20,
                pnl_minor=0,
                clv_ppm=None,
            ),
            "outcome": "PENDING",
        },
    )

    snapshot = build_research_analytics_snapshot(
        rows,
        fixed_stake_minor=30_000,
        as_of=AS_OF,
    )

    assert snapshot["contract_version"] == "RESEARCH_ANALYTICS_V1"
    assert snapshot["windows"]["lifetime"]["n"] == 2
    assert snapshot["windows"]["last_7d"]["n"] == 2
    assert snapshot["windows"]["last_30d"]["n"] == 2
    assert snapshot["weekly"][0]["week"] == "2026-W39"
    assert snapshot["cohorts"]["market_selection"]
    assert snapshot["cohorts"]["production_filter_cube"]

    diagnostic = {
        item["diagnostic"]: item for item in snapshot["diagnostics"]
    }
    assert diagnostic["LOW_SCORING_EXTREME"]["n"] == 1
    assert diagnostic["OTHER_NON_EXTREME"]["n"] == 1


def test_repository_list_all_signals_pages_until_history_is_exhausted() -> None:
    repository = PostgreSQLResearchSignalRepository(connect=lambda: None)
    calls = []

    def page(*, limit: int, offset: int):
        calls.append((limit, offset))
        values = ({"fixture_id": "1"}, {"fixture_id": "2"}, {"fixture_id": "3"})
        return values[offset : offset + limit]

    repository.list_signals = page  # type: ignore[method-assign]

    assert repository.list_all_signals(batch_size=2) == (
        {"fixture_id": "1"},
        {"fixture_id": "2"},
        {"fixture_id": "3"},
    )
    assert calls == [(2, 0), (2, 2)]
