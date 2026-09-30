# QuantBet — Value Calculation and Decision Contract

_Last synchronized: 2026-09-30_

## Status

The value, eligibility, registration and risk boundaries are implemented in Production. Earlier revisions of this document that described eligibility/de-vig/risk as future work are superseded.

## 1. Complete two-way market

Production value evaluation uses an exact complete two-way market observation.

Selections from different bookmaker observations/timestamps are not mixed for de-vig.

## 2. De-vig

The active Production method is versioned as:

`PROPORTIONAL_TWO_WAY_V1`

For raw implied probabilities `r_selected = 1 / odds_selected` and `r_companion = 1 / odds_companion`:

```text
overround = r_selected + r_companion
market_fair_probability = r_selected / overround
```

## 3. Value

For model probability `p` and selected decimal odds `o`:

```text
edge = p - market_fair_probability
expected_value = p * o - 1
```

Raw implied probability, de-vig probability, model probability, edge and EV are all persisted as separate facts.

## 4. Eligibility

Value calculation alone is not registration authority.

Eligibility/risk evaluates the active versioned policy, including:

- bookmaker/market/selection;
- de-vig method;
- edge;
- EV;
- odds;
- fixture status;
- quote freshness;
- time to kickoff;
- model state/coverage;
- risk/open exposure;
- duplicate/already-registered conditions.

Failures use stable rejection codes.

## 5. Final quote verification

A preliminarily acceptable candidate still requires final quote verification before durable registration.

Production fails closed when the required fresh/valid final market evidence is unavailable.

## 6. Registration provenance

Registered picks retain links to the decision/value/model/policy evidence used to authorize the pick.

Historical facts are not rewritten when later prices/results arrive.

## 7. Research boundary

Research preserves the preliminary comparable final-gate decision context so Production and exposure-blocked candidates are not compared at different quote stages.

## 8. Governance

Research/QuantLab analytics do not modify these policies automatically.

A bucket-based Production rule change requires explicit owner approval and an explicit version/configuration change.
