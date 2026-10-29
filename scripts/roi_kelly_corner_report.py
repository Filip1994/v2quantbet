"""Read-only 1xBet CornerLab ROI Kelly report, sourced from existing settlements.

Run from the QuantBet repository in the Engine/Railway environment:
    python -m scripts.roi_kelly_corner_report --bankroll-rsd 30000

No writes, no bets, no changes to Production intake. Quoted odds in the report
are bucket midpoints, not verified live offers; stake estimates are ILLUSTRATIVE.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

import psycopg

from h2h.corner_buckets import CORNER_OPERATIONS_BUCKETS
from h2h.domain.bookmaker_policy import is_production_bookmaker
from h2h.domain.competition_scope import is_universe_blocked_competition
from h2h.persistence.postgres_production_funnel import (
    PostgreSQLProductionFunnelRepository,
)
from h2h.production_buckets import matching_bucket_ids
from h2h.roi_kelly import calculate_roi_kelly


def make_report(rows: tuple[dict, ...], *, bankroll_minor: int) -> dict:
    by_id = {
        bucket.bucket_id: {
            "graded_n": 0, "wins": 0, "losses": 0, "historical_unit_pnl": 0.0
        } for bucket in CORNER_OPERATIONS_BUCKETS
    }
    excluded = defaultdict(int)
    for row in rows:
        if not is_production_bookmaker(
            row.get("bookmaker_id"), row.get("bookmaker_name")
        ):
            excluded["other_bookmaker"] += 1
            continue
        if is_universe_blocked_competition(
            country=row.get("country"),
            competition_name=row.get("competition_name"),
            league_id=row.get("league_id"),
            home_team=row.get("home_team"),
            away_team=row.get("away_team"),
        ):
            excluded["universe_block"] += 1
            continue
        outcome = str(row.get("outcome") or "").upper()
        stake_minor = int(row.get("stake_minor") or 0)
        if outcome not in {"WIN", "LOSS"} or stake_minor <= 0:
            excluded["not_graded"] += 1
            continue
        matches = matching_bucket_ids(row, source_universe="CORNERLAB")
        for bucket_id in matches:
            if bucket_id not in by_id:
                continue
            acc = by_id[bucket_id]
            acc["graded_n"] += 1
            acc["wins"] += outcome == "WIN"
            acc["losses"] += outcome == "LOSS"
            acc["historical_unit_pnl"] += int(row.get("pnl_minor") or 0) / stake_minor

    results = []
    for bucket in CORNER_OPERATIONS_BUCKETS:
        acc = by_id[bucket.bucket_id]
        low, high = (float(x) for x in bucket.odds)
        # Midpoint is ONLY an illustration. Real sizing requires the latest
        # verified quote for a particular upcoming match, not this midpoint.
        example_odds = (low + high) / 2.0
        decision = calculate_roi_kelly(
            bucket_id=bucket.bucket_id,
            wins=acc["wins"],
            losses=acc["losses"],
            historical_unit_pnl=acc["historical_unit_pnl"],
            quote_odds=example_odds,
            bankroll_minor=bankroll_minor,
            verified_one_xbet=True,
        )
        results.append({
            "bucket_id": bucket.bucket_id,
            "label": bucket.label,
            "paper_only": True,
            "bookmaker": "1xBet",
            "observed_win_rate_pct": (
                100 * acc["wins"] / acc["graded_n"]
                if acc["graded_n"] else None
            ),
            "historical_unit_pnl": acc["historical_unit_pnl"],
            "example_quote_not_live": example_odds,
            "roi_kelly_example": decision.as_dict(),
        })
    results.sort(key=lambda x: (
        -(x["roi_kelly_example"]["historical_roi_pct"]),
        -(x["roi_kelly_example"]["graded_n"]),
    ))
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "latest immutable CORNERLAB settlement per PAPER pick",
        "bookmaker": "1xBet ONLY",
        "stake_mode": "ILLUSTRATIVE_ONLY_NO_EXECUTION",
        "quote_warning": "Midpoint odds are NOT executable odds.",
        "limitations": [
            "This report is a current retrospective snapshot, not a walk-forward backtest.",
            "Only historical settled 1xBet PAPER picks are used.",
            "Historical positive ROI does not establish future positive EV.",
            "Kelly on future picks must use their actual bookmaker quote and only evidence available before decision time.",
            "Existing Production top-5 intake and bankroll are unchanged.",
        ],
        "excluded_rows": dict(excluded),
        "buckets": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bankroll-rsd", default="30000",
                        help="Illustrative bankroll in RSD (default: 30000)")
    args = parser.parse_args()
    bankroll = Decimal(args.bankroll_rsd)
    if not bankroll.is_finite() or bankroll <= 0:
        parser.error("bankroll must be positive and finite")
    bankroll_minor = int((bankroll * 100).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    ))
    url = os.environ.get("DATABASE_URL")
    if not url:
        parser.error("DATABASE_URL must be provided by the Railway environment")
    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            # Reuse the same historical source that Production uses to rank.
            rows = PostgreSQLProductionFunnelRepository._cornerlab_performance_rows(cursor)
            report = make_report(rows, bankroll_minor=bankroll_minor)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
