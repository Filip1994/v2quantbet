# QuantLab Roadmap

## Foundation — current

- separate Railway service
- separate API category
- shared shadow ledger
- three-tab dashboard
- repository architecture split into GoalLab / CornerLab / CardLab
- documentation and mandatory work log

## Phase 1 — market ingestion

Collect every supported pre-match market returned for Bet365 and 1xBet while preserving raw provider bet IDs/names/selections and timestamps.

## Phase 2 — lab feature stores

### GoalLab
DC+ core, recent form, home/away splits, rest and congestion.

### CornerLab
historical corners for/against, home/away splits, recent corner form and relevant attacking-pressure proxies.

### CardLab
team card/foul profile plus the five immediate context variables defined in `CardLab/FEATURES_V1.md`.

## Phase 3 — shadow models

Generate model probabilities, devig market probabilities, edge and EV without production writes.

## Phase 4 — settlement

Settle all supported market semantics and maintain flat-stake P&L, ROI, CLV and drawdown.

## Phase 5 — walk-forward evaluation

Compare model versions only with time-valid features and out-of-sample walk-forward evaluation.

## Promotion

Any production promotion requires a separate explicit decision and is outside QuantLab's automatic authority.
