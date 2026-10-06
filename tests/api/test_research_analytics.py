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
    model_version: str = "dcm-json-v1:" + "a" * 64,
    policy_config: str | None = "pick-policy-config-v1:" + "b" * 64,
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
        "edge_bucket": (
            "30%+" if edge >= 0.30 else
            "20–30%" if edge >= 0.20 else
            "15–20%" if edge >= 0.15 else
            "10–15%" if edge >= 0.10 else
            "5–10%" if edge >= 0.05 else
            "0–5%" if edge >= 0 else "<0%"
        ),
        "odds_bucket": "1.81–2.00",
        "time_to_kickoff_bucket": "1–3h",
        "disposition": "BLOCKED_EXPOSURE",
        "bookmaker": "Bet365",
        "model_version_id": model_version,
        "prediction_method_version": "DIXON_COLES_V1",
        "devig_method_version": "PROPORTIONAL_TWO_WAY_V1",
        "policy_config_fingerprint": policy_config,
        "eligibility_policy_version": "ELIGIBILITY_V1" if policy_config else None,
        "risk_policy_version": "RISK_V1" if policy_config else None,
        "staking_policy_version": "FIXED_STAKE_V1" if policy_config else None,
        "bookmaker_policy_version": "SERBIA_ALLOWLIST_V1" if policy_config else None,
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
    assert metrics["roi_95_low_pct"] is not None
    assert metrics["roi_95_high_pct"] is not None
    assert metrics["roi_95_low_pct"] < metrics["roi_pct"] < metrics["roi_95_high_pct"]
    assert metrics["roi_last_100_pct"] is None
    assert metrics["roi_last_250_pct"] is None
    assert metrics["roi_last_500_pct"] is None
    assert metrics["sample_band"] == "COLLECT"


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

    assert snapshot["contract_version"] == "RESEARCH_ANALYTICS_V2"
    assert snapshot["windows"]["lifetime"]["n"] == 2
    assert snapshot["windows"]["last_7d"]["n"] == 2
    assert snapshot["windows"]["last_30d"]["n"] == 2
    assert snapshot["weekly"][0]["week"] == "2026-W39"
    assert snapshot["cohorts"]["market_selection"]
    assert snapshot["cohorts"]["market_selection_odds"]
    assert snapshot["cohorts"]["market_selection_edge"]
    assert snapshot["cohorts"]["edge_bucket"]
    assert snapshot["cohorts"]["time_to_kickoff_bucket"]
    assert snapshot["cohorts"]["league_market"]
    assert "production_filter_cube" not in snapshot["cohorts"]
    assert snapshot["version_summary"]["mixed_model_versions"] is False
    assert snapshot["version_summary"]["mixed_policy_configs"] is False
    assert snapshot["cohorts"]["model_policy"][0]["graded_n"] == 2

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



def test_snapshot_flags_mixed_and_unrecorded_version_regimes() -> None:
    rows = (
        row(
            fixture="1",
            market="BTTS",
            selection="YES",
            outcome="WIN",
            model_probability=0.60,
            market_fair_probability=0.50,
            odds=2.0,
            edge=0.10,
            ev=0.20,
            pnl_minor=30_000,
            clv_ppm=10_000,
            model_version="dcm-json-v1:" + "1" * 64,
            policy_config="pick-policy-config-v1:" + "2" * 64,
        ),
        row(
            fixture="2",
            market="BTTS",
            selection="NO",
            outcome="LOSS",
            model_probability=0.60,
            market_fair_probability=0.50,
            odds=2.0,
            edge=0.10,
            ev=0.20,
            pnl_minor=-30_000,
            clv_ppm=-10_000,
            model_version="dcm-json-v1:" + "3" * 64,
            policy_config=None,
        ),
    )

    snapshot = build_research_analytics_snapshot(
        rows,
        fixed_stake_minor=30_000,
        as_of=AS_OF,
    )

    assert snapshot["version_summary"]["mixed_model_versions"] is True
    assert snapshot["version_summary"]["mixed_policy_configs"] is True
    assert snapshot["version_summary"]["unrecorded_policy_n"] == 1
    assert len(snapshot["cohorts"]["model_policy"]) == 2


def test_retired_low_price_under_stays_visible_but_is_excluded_from_active_aggregates() -> None:
    active = row(
        fixture="active",
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
    )
    retired = {
        **row(
            fixture="retired",
            market="OU_25",
            selection="UNDER",
            outcome="LOSS",
            model_probability=0.70,
            market_fair_probability=0.65,
            odds=1.70,
            edge=0.05,
            ev=0.10,
            pnl_minor=-30_000,
            clv_ppm=0,
        ),
        "odds_bucket": "1.61–1.80",
    }

    snapshot = build_research_analytics_snapshot(
        (active, retired),
        fixed_stake_minor=30_000,
        as_of=AS_OF,
    )

    lifetime = snapshot["windows"]["lifetime"]
    assert lifetime["graded_n"] == 1
    assert lifetime["wins"] == 1
    assert lifetime["losses"] == 0
    assert lifetime["flat_pnl_minor"] == 30_000
    assert lifetime["roi_pct"] == pytest.approx(100.0)

    market_rows = snapshot["cohorts"]["market_selection"]
    assert all(
        not (
            item["market"] == "OU_25"
            and item["selection"] == "UNDER"
        )
        for item in market_rows
    )

    odds_rows = snapshot["cohorts"]["market_selection_odds"]
    retired_row = next(
        item
        for item in odds_rows
        if item["market"] == "OU_25"
        and item["selection"] == "UNDER"
        and item["odds_bucket"] == "1.61–1.80"
    )
    assert retired_row["graded_n"] == 1
    assert retired_row["roi_pct"] == pytest.approx(-100.0)
