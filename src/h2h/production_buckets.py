"""Shared metadata for the Production intake bucket contract.

The order records the six historical promotion candidates, including retired cohorts.
The default live intake contains Research only; the GoalLab OVER cohorts retired on
2026-10-10 remain defined for historical analytics and possible future reapproval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
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

# Fail-safe default: GoalLab OVER buckets are retired from Production (2026-10-10).
# Historical specs stay known so evidence/links and explicit future promotions survive.
DEFAULT_BUCKET_IDS = tuple(
    spec.bucket_id for spec in PRODUCTION_BUCKET_SPECS if spec.source_universe == "RESEARCH"
)
KNOWN_BUCKET_IDS = frozenset(spec.bucket_id for spec in PRODUCTION_BUCKET_SPECS)
BUCKET_PRIORITY = {
    spec.bucket_id: index for index, spec in enumerate(PRODUCTION_BUCKET_SPECS, 1)
}
BUCKET_BY_ID = {spec.bucket_id: spec for spec in PRODUCTION_BUCKET_SPECS}


def bucket_spec(bucket_id: str) -> ProductionBucketSpec | None:
    return BUCKET_BY_ID.get(bucket_id)


def is_retired_research_segment(row: dict[str, Any]) -> bool:
    """Return whether a Research candidate is intentionally excluded from the universe."""
    market = str(row.get("market_key") or row.get("market") or "").upper()
    selection = str(row.get("selection") or row.get("selected_selection") or "").upper()
    odds = float(row.get("odds") or row.get("selected_odd") or 0)
    if market != "OU_25":
        return False
    if selection == "UNDER":
        return 1.40 <= odds <= 1.80
    if selection == "OVER":
        return 1.61 <= odds <= 1.80
    return False


def bucket_matches(row: dict[str, Any], bucket_id: str) -> bool:
    """Exact shared predicate for analytics, historical scoring and live intake."""
    market = str(row.get("market_key") or row.get("market") or "").upper()
    selection = str(row.get("selection") or "").upper()
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
    raise ValueError(f"unknown production bucket {bucket_id!r}")


def matching_bucket_ids(
    row: dict[str, Any],
    *,
    source_universe: str,
) -> tuple[str, ...]:
    source = source_universe.upper()
    if source == "RESEARCH" and is_retired_research_segment(row):
        return ()
    return tuple(
        spec.bucket_id
        for spec in PRODUCTION_BUCKET_SPECS
        if spec.source_universe == source and bucket_matches(row, spec.bucket_id)
    )


def n_roi_priority_score(*, graded_n: int, roi_pct: float | None) -> float:
    """ROI discounted by evidence depth until N=100; no extra N bonus after N=100."""
    if graded_n <= 0 or roi_pct is None:
        return float("-inf")
    return float(roi_pct) * min(1.0, graded_n / 100.0)
