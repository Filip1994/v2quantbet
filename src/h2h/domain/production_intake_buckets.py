"""Shared metadata and exact predicates for Production intake buckets.

The selected bucket set is owned outside Production execution. Production may use the
historical N + ROI evidence of these exact buckets to order intake, but it does not create
new betting-quality rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RESEARCH_LOW_SCORING_NON_EXTREME = "RESEARCH_LOW_SCORING_NON_EXTREME"
RESEARCH_OU_UNDER_EDGE_10_15 = "RESEARCH_OU_UNDER_EDGE_10_15"
RESEARCH_OU_UNDER_EDGE_20_30 = "RESEARCH_OU_UNDER_EDGE_20_30"
RESEARCH_BTTS_NO_ODDS_2_01_2_50 = "RESEARCH_BTTS_NO_ODDS_2_01_2_50"
GOALLAB_OU_OVER_XG_2_5_3_0 = "GOALLAB_OU_OVER_XG_2_5_3_0"
GOALLAB_OU_OVER_ODDS_2_01_2_50 = "GOALLAB_OU_OVER_ODDS_2_01_2_50"

DEFAULT_BUCKET_IDS = (
    RESEARCH_LOW_SCORING_NON_EXTREME,
    RESEARCH_OU_UNDER_EDGE_10_15,
    RESEARCH_OU_UNDER_EDGE_20_30,
    RESEARCH_BTTS_NO_ODDS_2_01_2_50,
    GOALLAB_OU_OVER_XG_2_5_3_0,
    GOALLAB_OU_OVER_ODDS_2_01_2_50,
)


@dataclass(frozen=True, slots=True)
class ProductionBucketSpec:
    bucket_id: str
    source_universe: str
    label: str
    definition: str
    quick_path: str


BUCKET_SPECS = {
    RESEARCH_LOW_SCORING_NON_EXTREME: ProductionBucketSpec(
        RESEARCH_LOW_SCORING_NON_EXTREME,
        "RESEARCH",
        "Low scoring · non-extreme",
        "OU 2.5 UNDER or BTTS NO; EV < 30% and edge < 20%",
        "Research → Analytics → Production intake buckets",
    ),
    RESEARCH_OU_UNDER_EDGE_10_15: ProductionBucketSpec(
        RESEARCH_OU_UNDER_EDGE_10_15,
        "RESEARCH",
        "OU UNDER · edge 10–15%",
        "OU 2.5 UNDER; edge ≥ 10% and < 15%",
        "Research → Analytics → Production intake buckets",
    ),
    RESEARCH_OU_UNDER_EDGE_20_30: ProductionBucketSpec(
        RESEARCH_OU_UNDER_EDGE_20_30,
        "RESEARCH",
        "OU UNDER · edge 20–30%",
        "OU 2.5 UNDER; edge ≥ 20% and < 30%",
        "Research → Analytics → Production intake buckets",
    ),
    RESEARCH_BTTS_NO_ODDS_2_01_2_50: ProductionBucketSpec(
        RESEARCH_BTTS_NO_ODDS_2_01_2_50,
        "RESEARCH",
        "BTTS NO · odds 2.01–2.50",
        "BTTS NO; entry odds > 2.00 and ≤ 2.50",
        "Research → Analytics → Production intake buckets",
    ),
    GOALLAB_OU_OVER_XG_2_5_3_0: ProductionBucketSpec(
        GOALLAB_OU_OVER_XG_2_5_3_0,
        "GOALLAB",
        "OU OVER · xG total 2.5–3.0",
        "GoalLab OU 2.5 OVER; expected total goals ≥ 2.5 and < 3.0",
        "QuantLab → GoalLab → Analytics → Production intake buckets",
    ),
    GOALLAB_OU_OVER_ODDS_2_01_2_50: ProductionBucketSpec(
        GOALLAB_OU_OVER_ODDS_2_01_2_50,
        "GOALLAB",
        "OU OVER · odds 2.01–2.50",
        "GoalLab OU 2.5 OVER; entry odds > 2.00 and ≤ 2.50",
        "QuantLab → GoalLab → Analytics → Production intake buckets",
    ),
}


def bucket_spec(bucket_id: str) -> ProductionBucketSpec:
    try:
        return BUCKET_SPECS[bucket_id]
    except KeyError as exc:
        raise ValueError(f"unknown production intake bucket {bucket_id!r}") from exc


def bucket_anchor(bucket_id: str) -> str:
    return "production-bucket-" + bucket_id.casefold().replace("_", "-")


def _market(row: dict[str, Any]) -> str:
    return str(row.get("market_key") or row.get("market") or "").upper()


def _selection(row: dict[str, Any]) -> str:
    return str(row.get("selection") or "").upper()


def bucket_matches(row: dict[str, Any], bucket_id: str) -> bool:
    market = _market(row)
    selection = _selection(row)
    odds = float(row.get("odds") or 0)
    edge = float(row.get("edge") or 0)
    ev = float(row.get("expected_value") or 0)

    if bucket_id == RESEARCH_LOW_SCORING_NON_EXTREME:
        low_scoring = (market == "OU_25" and selection == "UNDER") or (
            market == "BTTS" and selection == "NO"
        )
        return low_scoring and ev < 0.30 and edge < 0.20
    if bucket_id == RESEARCH_OU_UNDER_EDGE_10_15:
        return market == "OU_25" and selection == "UNDER" and 0.10 <= edge < 0.15
    if bucket_id == RESEARCH_OU_UNDER_EDGE_20_30:
        return market == "OU_25" and selection == "UNDER" and 0.20 <= edge < 0.30
    if bucket_id == RESEARCH_BTTS_NO_ODDS_2_01_2_50:
        return market == "BTTS" and selection == "NO" and 2.00 < odds <= 2.50
    if bucket_id == GOALLAB_OU_OVER_XG_2_5_3_0:
        home = row.get("expected_home_goals")
        away = row.get("expected_away_goals")
        if home is None or away is None:
            return False
        total = float(home) + float(away)
        return market == "OU_25" and selection == "OVER" and 2.5 <= total < 3.0
    if bucket_id == GOALLAB_OU_OVER_ODDS_2_01_2_50:
        return market == "OU_25" and selection == "OVER" and 2.00 < odds <= 2.50
    raise ValueError(f"unknown production intake bucket {bucket_id!r}")


def matching_bucket_ids(
    row: dict[str, Any],
    *,
    source_universe: str,
) -> tuple[str, ...]:
    source = source_universe.upper()
    return tuple(
        bucket_id
        for bucket_id in DEFAULT_BUCKET_IDS
        if BUCKET_SPECS[bucket_id].source_universe == source
        and bucket_matches(row, bucket_id)
    )


def n_roi_priority_score(*, graded_n: int, roi_pct: float | None) -> float:
    """Transparent intake ordering: ROI discounted only by sample size until N reaches 100."""
    if graded_n <= 0 or roi_pct is None:
        return float("-inf")
    evidence_weight = min(1.0, graded_n / 100.0)
    return float(roi_pct) * evidence_weight
