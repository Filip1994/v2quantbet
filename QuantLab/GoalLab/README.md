# GoalLab

_Last synchronized: 2026-09-30_

GoalLab is QuantLab's isolated pre-match goals/BTTS research system. It does not write Production registered picks, Production bankroll or active Production model state.

## Current model

- model: **DC+ Pro Structural**
- prefix: `DC_PLUS_PRO_STRUCTURAL_V3:`
- structural feature version: `GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V2`
- evaluation policy family: `GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V5`
- canonical pick policy family: `GOALLAB_DC_PLUS_PICK_POLICY_V4`

## V2 structural contract

The old V1 readiness review found a 669-active-column / 792-example dimensionality problem.

That is historical evidence, not the current model shape.

V2 fixes it by using:

- a compact predeclared core feature contract;
- minimum feature-observation requirements;
- train-fold mean imputation;
- no per-feature missing-dummy explosion;
- ridge regularization;
- stronger interaction penalty;
- timestamp-safe rolling/venue/opponent/context features;
- no bookmaker odds in the probability model;
- no target-match live statistics;
- no target fixture player response leakage.

## Markets

Canonical GoalLab markets:

- O/U 2.5 OVER / UNDER;
- BTTS YES / NO.

De-vig uses a complete same-bookmaker same-capture two-way market.

## Canonical pick

GoalLab evaluates all supported candidate decisions but persists exactly one canonical GoalLab pick per fixture/pick-policy version after deterministic ranking. Non-selected decisions remain immutable evidence.

## Validation and authority

Chronological validation compares DC+ with control Dixon-Coles and runs an explicit leakage audit.

GoalLab pick authority is exact-model-hash controlled. A new model hash does not inherit approval automatically.

Validation metrics are evidence for manual authority; they do not prove profitability.

## Analytics

GoalLab Analytics starts with **Watchlist · ROI discovery**:

- Goal shape × price;
- Balance × total-line gap;
- Model vs market × price;
- Trend × matchup;
- Reliability × market.

Buckets drill down to the exact settled picks behind the row. Broader tables cover price, probability, EV, lambda shape/balance, trend, matchup, reliability and other measurable dimensions.

## Production governance

GoalLab itself has no Production authority.

If a GoalLab/Research bucket is to influence Production selection, the owner must explicitly approve and implement the rule outside the GoalLab write boundary. A mandatory forward/OOS waiting period is not required for owner approval.

See [../../docs/CURRENT_PRIORITIES.md](../../docs/CURRENT_PRIORITIES.md).
