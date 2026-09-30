# QuantLab

_Last synchronized: 2026-09-30_

QuantLab is QuantBet's isolated multi-market model laboratory.

It is not the Production registration/risk engine and it is not the Production-comparable Research universe.

## Laboratories

- [GoalLab](./GoalLab/README.md) — goals, BTTS and DC+ Structural research.
- [CornerLab](./CornerLab/README.md) — corner totals and structural pressure models.
- [CardLab](./CardLab/README.md) — cards/referee/context research.

## Runtime

Runtime code: `src/h2h/quantlab/`.

Railway currently separates the QuantLab web/runtime, modeler and collector responsibilities into dedicated services.

All QuantLab persistence is QuantLab-owned. Production registered picks, bankroll, decision records and active Production model state are outside its write boundary.

## Shared rules

- timestamp-safe feature availability;
- no post-kickoff leakage into pre-match models;
- immutable/versioned decision evidence;
- exact provider/bookmaker/market provenance;
- shared provider-budget telemetry;
- PostgreSQL durability;
- read-only HTTP dashboard actions.

## Current analytics

GoalLab and CornerLab have a dedicated **Watchlist · ROI discovery** block before the broader analytics tables.

Watchlist cohorts drill down to the exact settled picks and analytics headers are sortable.

### GoalLab watchlist

- Goal shape × price
- Balance × total-line gap
- Model vs market × price
- Trend × matchup
- Reliability × market

### CornerLab watchlist

- Model-line gap × price
- Pressure trend × matchup
- Model vs market × price
- Reliability × market

## Production boundary

QuantLab never auto-promotes a bucket/model into Production.

An explicit owner decision is required for any Production use. Forward/OOS evidence is useful but not a mandatory owner-approval gate.

See [../docs/CURRENT_PRIORITIES.md](../docs/CURRENT_PRIORITIES.md).
