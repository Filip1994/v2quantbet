# QuantBet — Value Calculation and Decision Contract

**Status:** Contract v1 draft — documents current behavior and required production boundary
**Date:** 2026-09-15

## 1. Scope

This document defines the boundary between deterministic value calculation and future `ValuePick` eligibility. The current calculation is not, by itself, an authorization to publish or place a bet.

## 2. Current deterministic calculation

For a canonical quote with decimal odds `o` and model probability `p`:

```text
implied_probability = 1 / o
probability_gap = p - implied_probability
expected_value = p * o - 1
```

The current implementation expresses `probability_gap` as a decimal probability difference. For example, `0.1737` means `+17.37` percentage points.

The model probability must be finite and within the closed interval `[0, 1]`. Invalid values are rejected.

## 3. Important boundary

The current calculation uses **raw implied probability**. It does not remove bookmaker margin and does not estimate a de-vig probability. Therefore, the result must not be described as a margin-adjusted market edge.

A positive `expected_value` is a mathematical output, not sufficient evidence for publishing a production pick.

## 4. Required eligibility layer

A separate decision layer must eventually evaluate at least:

- supported bookmaker policy;
- market and selection identity;
- quote freshness;
- stale or conflicting quote status;
- minimum and maximum odds;
- minimum expected value;
- minimum probability gap;
- model/data quality flags;
- model and configuration version;
- availability of the complete market where de-vig is required;
- duplicate-pick and already-published state;
- time-to-kickoff restrictions;
- risk and stake policy.

Every rejection must have a stable machine-readable reason code.

## 5. Margin/de-vig policy — unresolved

The project has not yet selected a universal de-vig method. Until that decision is made:

- raw implied probability remains the explicitly named calculation;
- no component may silently label raw implied probability as de-vig probability;
- incomplete markets must not be treated as complete markets;
- any future de-vig implementation requires tests and a documented method/version.

## 6. Rounding and numeric policy — unresolved

The production contract still needs explicit rules for:

- internal precision;
- serialization precision;
- display rounding;
- comparison thresholds near zero;
- treatment of non-finite odds or derived values.

Comparisons should be performed before display rounding.

## 7. Required provenance

A future registered pick must preserve, at minimum:

- quote identity and snapshot reference;
- decision timestamp;
- model probability;
- raw implied probability;
- expected value;
- probability gap;
- model version;
- configuration version;
- applied eligibility rules;
- rejection or acceptance reason;
- data-quality and freshness flags.

## 8. Decision

Keep the existing deterministic `evaluate_value()` behavior unchanged. Build the eligibility and registration boundary around it rather than expanding the current function into an implicit betting decision engine.
