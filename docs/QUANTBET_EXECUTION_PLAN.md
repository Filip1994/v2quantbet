# QuantBet — Current Execution Plan

_Last synchronized: 2026-09-30_

This replaces the original phase plan as the current execution sequence. Historical Git versions preserve the earlier bulletin-first planning record.

## Stage A — Production core

**Status: operational.**

Implemented:

- fixture discovery;
- historical model training lifecycle;
- odds ingestion;
- model prediction/value;
- eligibility/risk/final verification;
- durable registration;
- bulletin;
- monitoring/closing;
- settlement/bankroll/CLV;
- production dashboard/operator state.

Remaining work is primarily reliability, coverage and release governance.

## Stage B — Research Universe

**Status: operational.**

Implemented:

- final-gate canonical candidate capture;
- PLAYED / SKIPPED / BLOCKED_EXPOSURE routes;
- counterfactual flat-stake settlement;
- same-book closing/CLV where available;
- bucket/cohort analytics;
- model/policy regime analytics;
- drilldowns to exact picks.

Next:

- richer uncertainty/stability views;
- clearer funnel/coverage diagnostics;
- continued owner-driven Production review.

## Stage C — QuantLab

**Status: operational research platform.**

### GoalLab

- DC+ Pro Structural V3;
- compact V2 feature contract;
- chronological validation;
- exact-hash manual authority;
- canonical GoalLab picks/settlement;
- deep analytics + Watchlist.

### CornerLab

- pressure-Poisson V2;
- structural pre-match features;
- corner settlement/analytics;
- Watchlist.

Primary next task: data/coverage and bookmaker-aligned historical evaluation.

### CardLab

- referee-Poisson V1;
- 1xBet Cards Over/Under path;
- append-only settlement evidence.

Primary next task: referee/card data coverage and stronger statistical pooling.

## Stage D — release discipline

Highest-priority engineering sequence:

1. restore green CI;
2. run full pytest after lint passes;
3. deploy only CI-validated SHAs;
4. expose deployed SHA / deployment time / CI state;
5. keep production changes explicit and versioned.

## Stage E — evidence quality

1. GoalLab league-specific vs pooled-control validation split;
2. macro-by-league GoalLab reporting;
3. CornerLab coverage funnel and historical aligned odds evaluation;
4. CardLab data coverage;
5. ROI uncertainty/stability evidence;
6. identity-conflict and model-fit failure telemetry.

## Stage F — maintainability

Incrementally split large modules and introduce typed boundary models. No rewrite.

## Owner decision boundary

Research and QuantLab can propose evidence, never automatic Production changes.

A bucket can be promoted after explicit owner approval. Forward/OOS evidence is advisory, not mandatory.

Performance-based bucket bans should normally wait 3–6 months; technical-integrity failures are exempt and may be suspended immediately.

See [CURRENT_PRIORITIES.md](./CURRENT_PRIORITIES.md).
