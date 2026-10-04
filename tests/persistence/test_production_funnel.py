from __future__ import annotations

import pytest

from h2h.persistence.postgres_production_funnel import (
    DEFAULT_BUCKET_IDS,
    GOALLAB_OU_OVER_ODDS_2_01_2_50,
    GOALLAB_OU_OVER_XG_2_5_3_0,
    RESEARCH_BTTS_NO_ODDS_2_01_2_50,
    RESEARCH_LOW_SCORING_NON_EXTREME,
    RESEARCH_OU_UNDER_EDGE_10_15,
    RESEARCH_OU_UNDER_EDGE_20_30,
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
        RESEARCH_LOW_SCORING_NON_EXTREME,
        GOALLAB_OU_OVER_ODDS_2_01_2_50,
    )


def test_intake_contract_rejects_unknown_bucket() -> None:
    with pytest.raises(ValueError, match="unknown production intake bucket"):
        active_bucket_ids({"QUANTBET_PRODUCTION_INTAKE_BUCKETS": "NOT_A_BUCKET"})


def test_contract_version_changes_when_active_bucket_set_changes() -> None:
    full = intake_contract_version(DEFAULT_BUCKET_IDS)
    subset = intake_contract_version(DEFAULT_BUCKET_IDS[:2])

    assert full.startswith("PRODUCTION_FUNNEL_INTAKE_V2:")
    assert full != subset


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

    assert matches == (
        RESEARCH_LOW_SCORING_NON_EXTREME,
        RESEARCH_OU_UNDER_EDGE_10_15,
    )


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


def test_candidate_ranking_is_global_not_bucket_priority() -> None:
    rows = [
        {
            "source_universe": "RESEARCH",
            "source_pick_id": "research-low-ev",
            "expected_value": 0.12,
            "edge": 0.18,
            "source_decision_at": 1,
        },
        {
            "source_universe": "GOALLAB",
            "source_pick_id": "goallab-high-ev",
            "expected_value": 0.31,
            "edge": 0.16,
            "source_decision_at": 2,
        },
        {
            "source_universe": "GOALLAB",
            "source_pick_id": "goallab-same-ev-higher-edge",
            "expected_value": 0.31,
            "edge": 0.20,
            "source_decision_at": 3,
        },
    ]

    ordered = sorted(
        rows,
        key=PostgreSQLProductionFunnelRepository._candidate_sort_key,
    )

    assert [row["source_pick_id"] for row in ordered] == [
        "goallab-same-ev-higher-edge",
        "goallab-high-ev",
        "research-low-ev",
    ]
