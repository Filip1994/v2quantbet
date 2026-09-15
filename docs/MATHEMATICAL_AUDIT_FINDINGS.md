# QuantBet — Mathematical Audit Findings

**Status:** Audit record / implementation priorities
**Date:** 2026-09-15

## Executive conclusion

The Dixon–Coles implementation should remain unchanged for now. Existing regression protection supports the conclusion that the implementation is reproducibility-locked against the legacy baseline. This does **not** establish calibration, profitability, robustness, superiority over a market baseline, or suitability for autonomous betting decisions.

The appropriate current label is:

> Reproducibility-Locked Dixon–Coles Baseline

The stronger label `Frozen Mathematical Baseline` should be used only after the complete mathematical contract is explicitly specified and verified.

## Confirmed strengths

- Dixon–Coles remains a reasonable interpretable starting model for football score probabilities.
- Existing golden-master protection should not be changed without an explicit baseline comparison.
- Model replacement with a more complex ML architecture is not justified without out-of-sample evidence.
- Reproducibility and predictive validity are separate acceptance criteria.

## Main gaps

### 1. Complete model contract

The following still require explicit specification:

- objective function;
- parameterization and identification constraints;
- initial values and parameter bounds;
- optimizer and convergence criteria;
- failed-optimization behavior;
- treatment of extreme scores and numerical failures;
- time weighting, if any;
- minimum historical sample requirements;
- new-team behavior;
- exact data and code version used for fitting.

### 2. Score-probability contract

The score matrix contract must define:

- matrix limits;
- truncation policy and error tolerance;
- normalization policy;
- numerical validity checks;
- probability-sum tolerance;
- behavior for invalid or non-finite output.

### 3. Market-probability contract

Every supported market must define its outcome set, formula, matrix dependency, and consistency checks. This currently applies at minimum to:

- `OVER_2.5`;
- `UNDER_2.5`;
- `BTTS_YES`.

The repository documentation already identifies a market-probability derivation stage and specifies complementary over/under behavior. However, the audit has not yet established that this contract is enforced end-to-end at the production decision boundary. The next code audit must locate the concrete implementation, verify its numerical guards, and test that the market probability passed to value evaluation is the intended probability for the exact quote selection.

### 4. Value-calculation contract

The system must distinguish raw implied probability from de-vig probability and explicitly define:

- bookmaker-margin treatment;
- supported comparison conditions;
- minimum and maximum odds;
- minimum EV and probability-gap thresholds;
- quote freshness and stale-quote rules;
- rounding policy;
- incomplete-market behavior;
- model-uncertainty handling.

A positive raw EV must not automatically imply an eligible `ValuePick`.

### 5. Data-quality and leakage contract

Before predictive validation, the dataset contract must address:

- chronological availability of every feature;
- duplicate and conflicting records;
- team and competition normalization;
- postponed and cancelled fixtures;
- promoted/relegated or new teams;
- retroactive data changes;
- minimum sample requirements;
- prevention of look-ahead leakage.

### 6. Predictive-validation contract

The validation layer must eventually include:

- chronological train/validation/test separation;
- walk-forward evaluation;
- log loss;
- Brier score;
- reliability analysis;
- calibration slope/intercept where sample size permits;
- results by market, league, period, and odds range;
- comparison against a clearly defined market or simple statistical baseline;
- uncertainty intervals and minimum sample rules.

## Product priority correction

The next priority should not be a large collection of disconnected mathematical documents. The highest-value next step is to implement and test the first complete production decision path:

```text
validated fixture/odds data
→ model probability
→ market probability
→ value evaluation
→ decision filters
→ immutable ValuePick registration
→ bulletin output
→ quote monitoring
→ closing reference
```

The mathematical contracts should be documented incrementally alongside that vertical slice.

## Current delivery assessment

| Area | Assessment |
|---|---|
| Dixon–Coles reproducibility | Good relative to legacy baseline |
| Predictive validity | Not demonstrated |
| Calibration | Not sufficiently demonstrated |
| Data-quality contract | Incomplete |
| Value decision service | Key implementation gap |
| Immutable pick registration | Key implementation gap |
| Quote lifecycle and closing reference | In progress |
| PostgreSQL foundation | In progress; real-DB verification remains |
| End-to-end bulletin-to-kickoff flow | Not yet demonstrated |
| Dashboard | Not currently a blocker |

## Decision

Do not modify the Dixon–Coles mathematics at this stage. Proceed with the value-evaluation service, immutable pick registration, and an end-to-end testable bulletin-to-kickoff lifecycle. Any future model change requires a reproducible experiment, chronological out-of-sample evaluation, and comparison against this baseline.

## Audit checkpoint — 2026-09-15

- `CanonicalQuote` validates supported market/selection combinations and basic odds integrity.
- `evaluate_value()` currently calculates raw implied probability, probability gap, and expected value deterministically.
- No production eligibility decision is represented by `ValuePick` itself; positive EV is therefore only a valuation result, not an approval to publish or bet.
- No dedicated provider-neutral eligibility service or stable rejection-code contract was found during this checkpoint.
- The next implementation step is to define the smallest explicit eligibility boundary without inventing undocumented thresholds or silently changing the existing value mathematics.
