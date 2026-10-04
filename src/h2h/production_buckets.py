"""Shared metadata for the Production intake bucket contract.

The order is intentional: it is the current ROI priority of the six approved buckets.
Presentation layers use the same IDs, labels and analytics drilldown paths so Production
links always resolve to the cohort that admitted the pick.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode


RESEARCH_LOW_SCORING_NON_EXTREME = "RESEARCH_LOW_SCORING_NON_EXTREME"
RESEARCH_OU_UNDER_EDGE_10_15 = "RESEARCH_OU_UNDER_EDGE_10_15"
RESEARCH_OU_UNDER_EDGE_20_30 = "RESEARCH_OU_UNDER_EDGE_20_30"
RESEARCH_BTTS_NO_ODDS_2_01_2_50 = "RESEARCH_BTTS_NO_ODDS_2_01_2_50"
GOALLAB_OU_OVER_XG_2_5_3_0 = "GOALLAB_OU_OVER_XG_2_5_3_0"
GOALLAB_OU_OVER_ODDS_2_01_2_50 = "GOALLAB_OU_OVER_ODDS_2_01_2_50"


@dataclass(frozen=True, slots=True)
class ProductionBucketSpec:
    bucket_id: str
    label: str
    source_universe: str
    analytics_path: str
    reference_roi_pct: float


def _research_path(**params: str) -> str:
    return "/research?" + urlencode({"tab": "history", **params})


def _goal_path(**params: str) -> str:
    return "/quantlab?" + urlencode(
        {"view": "analytics", "lab": "goal", "bucket": "1", **params}
    ) + "#bucket-picks"


PRODUCTION_BUCKET_SPECS = (
    ProductionBucketSpec(
        RESEARCH_OU_UNDER_EDGE_10_15,
        "OU UNDER · edge 10–15%",
        "RESEARCH",
        _research_path(market="OU_25", selection="UNDER", edge_bucket="10–15%"),
        32.19,
    ),
    ProductionBucketSpec(
        RESEARCH_OU_UNDER_EDGE_20_30,
        "OU UNDER · edge 20–30%",
        "RESEARCH",
        _research_path(market="OU_25", selection="UNDER", edge_bucket="20–30%"),
        22.55,
    ),
    ProductionBucketSpec(
        RESEARCH_BTTS_NO_ODDS_2_01_2_50,
        "BTTS NO · odds 2.01–2.50",
        "RESEARCH",
        _research_path(market="BTTS", selection="NO", odds_bucket="2.01–2.50"),
        20.59,
    ),
    ProductionBucketSpec(
        GOALLAB_OU_OVER_XG_2_5_3_0,
        "OU OVER · λ total 2.5–3.0",
        "GOALLAB",
        _goal_path(
            bucket_market_key="OU_25",
            bucket_selection="OVER",
            bucket_expected_total_goals_bucket="2.5–3",
        ),
        17.96,
    ),
    ProductionBucketSpec(
        GOALLAB_OU_OVER_ODDS_2_01_2_50,
        "OU OVER · odds 2.01–2.50",
        "GOALLAB",
        _goal_path(
            bucket_market_key="OU_25",
            bucket_selection="OVER",
            bucket_entry_odds_bucket="2.01–2.50",
        ),
        17.00,
    ),
    ProductionBucketSpec(
        RESEARCH_LOW_SCORING_NON_EXTREME,
        "Low scoring · non-extreme",
        "RESEARCH",
        _research_path(diagnostic="LOW_SCORING_NON_EXTREME"),
        10.29,
    ),
)

DEFAULT_BUCKET_IDS = tuple(spec.bucket_id for spec in PRODUCTION_BUCKET_SPECS)
KNOWN_BUCKET_IDS = frozenset(DEFAULT_BUCKET_IDS)
BUCKET_PRIORITY = {bucket_id: index for index, bucket_id in enumerate(DEFAULT_BUCKET_IDS, 1)}
BUCKET_BY_ID = {spec.bucket_id: spec for spec in PRODUCTION_BUCKET_SPECS}


def bucket_spec(bucket_id: str) -> ProductionBucketSpec | None:
    return BUCKET_BY_ID.get(bucket_id)
