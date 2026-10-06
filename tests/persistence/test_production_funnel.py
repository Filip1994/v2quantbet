from __future__ import annotations

import pytest

from h2h.production_buckets import (
    DEFAULT_BUCKET_IDS,
    GOALLAB_OU_OVER_ODDS_2_01_2_50,
    GOALLAB_OU_OVER_XG_2_5_3_0,
    RESEARCH_BTTS_NO_ODDS_2_01_2_50,
    RESEARCH_LOW_SCORING_NON_EXTREME,
    RESEARCH_OU_UNDER_EDGE_10_15,
    RESEARCH_OU_UNDER_EDGE_20_30,
    is_retired_research_segment,
    n_roi_priority_score,
)
from h2h.persistence.postgres_production_funnel import (
    PostgreSQLProductionFunnelRepository,
    active_bucket_ids,
    intake_contract_version,
)


def test_default_intake_contract_is_the_current_first_six_buckets() -> None:
    assert active_bucket_ids({}) == DEFAULT_BUCKET_IDS
    assert len(DEFAULT_BUCKET_IDS) == 6


def test_intake_contract_can_change_by_environment_without_core_code_change() -> None:
    values = {
        "QUANTBET_PRODUCTION_INTAKE_BUCKETS": (
            f"{GOALLAB_OU_OVER_ODDS_2_01_2_50},"
            f"{RESEARCH_LOW_SCORING_NON_EXTREME}"
        )
    }

    assert active_bucket_ids(values) == (
        GOALLAB_OU_OVER_ODDS_2_01_2_50,
        RESEARCH_LOW_SCORING_NON_EXTREME,
    )


def test_intake_contract_rejects_unknown_bucket() -> None:
    with pytest.raises(ValueError, match="unknown production intake bucket"):
        active_bucket_ids({"QUANTBET_PRODUCTION_INTAKE_BUCKETS": "NOT_A_BUCKET"})


def test_contract_version_changes_when_active_bucket_set_changes() -> None:
    full = intake_contract_version(DEFAULT_BUCKET_IDS)
    subset = intake_contract_version(DEFAULT_BUCKET_IDS[:2])

    assert full.startswith("PRODUCTION_FUNNEL_INTAKE_V3:")
    assert full != subset




@pytest.mark.parametrize(
    ("odds", "retired"),
    [
        (1.39, False),
        (1.40, True),
        (1.60, True),
        (1.61, True),
        (1.80, True),
        (1.81, False),
    ],
)
def test_low_price_under_research_segments_are_retired(odds: float, retired: bool) -> None:
    row = {
        "market_key": "OU_25",
        "selection": "UNDER",
        "odds": odds,
        "edge": 0.12,
        "expected_value": 0.18,
    }

    assert is_retired_research_segment(row) is retired
    if retired:
        assert PostgreSQLProductionFunnelRepository._research_matches(row) == ()


def test_research_low_scoring_non_extreme_can_overlap_edge_10_15() -> None:
    matches = PostgreSQLProductionFunnelRepository._research_matches(
        {
            "market_key": "OU_25",
            "selection": "UNDER",
            "odds": 1.95,
            "edge": 0.12,
            "expected_value": 0.18,
        }
    )

    assert set(matches) == {
        RESEARCH_LOW_SCORING_NON_EXTREME,
        RESEARCH_OU_UNDER_EDGE_10_15,
    }


def test_research_edge_20_30_is_extreme_not_non_extreme() -> None:
    matches = PostgreSQLProductionFunnelRepository._research_matches(
        {
            "market_key": "OU_25",
            "selection": "UNDER",
            "odds": 2.10,
            "edge": 0.24,
            "expected_value": 0.10,
        }
    )

    assert matches == (RESEARCH_OU_UNDER_EDGE_20_30,)


@pytest.mark.parametrize(
    ("odds", "included"),
    [
        (2.00, False),
        (2.01, True),
        (2.50, True),
        (2.51, False),
    ],
)
def test_research_btts_no_price_bucket_boundaries(odds: float, included: bool) -> None:
    matches = PostgreSQLProductionFunnelRepository._research_matches(
        {
            "market_key": "BTTS",
            "selection": "NO",
            "odds": odds,
            "edge": 0.05,
            "expected_value": 0.10,
        }
    )

    assert (RESEARCH_BTTS_NO_ODDS_2_01_2_50 in matches) is included


def test_goallab_over_can_match_shape_and_price_buckets_together() -> None:
    matches = PostgreSQLProductionFunnelRepository._goallab_matches(
        {
            "market_key": "OU_25",
            "selection": "OVER",
            "odds": 2.20,
            "expected_home_goals": 1.55,
            "expected_away_goals": 1.10,
        }
    )

    assert matches == (
        GOALLAB_OU_OVER_XG_2_5_3_0,
        GOALLAB_OU_OVER_ODDS_2_01_2_50,
    )


@pytest.mark.parametrize(
    ("total", "included"),
    [
        (2.49, False),
        (2.50, True),
        (2.99, True),
        (3.00, False),
    ],
)
def test_goallab_expected_total_bucket_boundaries(
    total: float, included: bool
) -> None:
    matches = PostgreSQLProductionFunnelRepository._goallab_matches(
        {
            "market_key": "OU_25",
            "selection": "OVER",
            "odds": 1.90,
            "expected_home_goals": total / 2,
            "expected_away_goals": total / 2,
        }
    )

    assert (GOALLAB_OU_OVER_XG_2_5_3_0 in matches) is included


def test_default_bucket_order_is_stable_contract_order() -> None:
    assert DEFAULT_BUCKET_IDS == (
        RESEARCH_OU_UNDER_EDGE_10_15,
        RESEARCH_OU_UNDER_EDGE_20_30,
        RESEARCH_BTTS_NO_ODDS_2_01_2_50,
        GOALLAB_OU_OVER_XG_2_5_3_0,
        GOALLAB_OU_OVER_ODDS_2_01_2_50,
        RESEARCH_LOW_SCORING_NON_EXTREME,
    )


def test_candidate_ranking_prefers_bucket_roi_before_pick_ev() -> None:
    research = {
        "source_universe": "RESEARCH",
        "source_pick_id": "research-top-bucket",
        "expected_value": 0.12,
        "edge": 0.11,
        "source_decision_at": 1,
    }
    goallab = {
        "source_universe": "GOALLAB",
        "source_pick_id": "goallab-higher-ev",
        "expected_value": 0.31,
        "edge": 0.20,
        "source_decision_at": 2,
    }

    ordered = sorted(
        [(1, research), (4, goallab)],
        key=lambda item: PostgreSQLProductionFunnelRepository._candidate_sort_key(
            item[0], item[1]
        ),
    )

    assert [row["source_pick_id"] for _priority, row in ordered] == [
        "research-top-bucket",
        "goallab-higher-ev",
    ]


def test_n_roi_priority_score_discounts_small_samples_until_n_100() -> None:
    assert n_roi_priority_score(graded_n=100, roi_pct=10.0) == pytest.approx(10.0)
    assert n_roi_priority_score(graded_n=25, roi_pct=32.0) == pytest.approx(8.0)
    assert n_roi_priority_score(graded_n=250, roi_pct=10.0) == pytest.approx(10.0)


def test_bucket_strength_prefers_better_n_roi_combination() -> None:
    stats = {
        RESEARCH_LOW_SCORING_NON_EXTREME: {
            "graded_n": 100,
            "roi_pct": 10.0,
            "priority_score": 10.0,
        },
        RESEARCH_OU_UNDER_EDGE_10_15: {
            "graded_n": 25,
            "roi_pct": 32.0,
            "priority_score": 8.0,
        },
    }

    strongest = max(
        stats,
        key=lambda bucket_id: PostgreSQLProductionFunnelRepository._bucket_strength_key(
            bucket_id,
            stats,
        ),
    )

    assert strongest == RESEARCH_LOW_SCORING_NON_EXTREME
