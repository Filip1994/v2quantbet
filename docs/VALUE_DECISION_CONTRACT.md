# QuantBet — Value Calculation and Decision Contract

**Status:** Structural decision/registration boundary implemented; acceptance policy remains undefined
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

## 9. Implemented structural boundary

```text
ValuePick -> EligibilityDecision -> register_pick() -> PickRegistration
```

`src/h2h/decisions/pick_eligibility.py` defines immutable `EligibilityDecision`
and `EligibilityStatus` (`APPROVED` or `REJECTED`). A decision requires an explicit
nonblank string `decision_id` and holds the exact `ValuePick` instance supplied
by its caller. There is no eligibility evaluator or implicit EV check.

Rejected decisions require a stable machine-readable `rejection_reason` matching
`[A-Z][A-Z0-9_]*`. Approved decisions require `rejection_reason=None`. The token
format is structural; no production reason vocabulary or betting rules have
been defined. Future policies own the codes and must keep their meanings stable.

`src/h2h/use_cases/register_pick.py::register_pick(decision, *, pick_id,
registered_at)` rejects a plain valuation and raises
`RejectedPickRegistrationError` for rejected decisions. For approval it stores
the decision's exact valuation and ID; callers cannot supply a replacement
valuation. Pick ID and registration-time validation remain in `PickRegistration`.

`PickRegistration.eligibility_decision_id` is the minimal provenance link to the
explicit approved decision consumed by this use-case. Direct domain construction
remains available, with this field defaulting to `None`; it does not demonstrate
that the gate ran. The link is not authentication or durable proof: no decision
repository, ID uniqueness service, policy execution, or publisher is implemented.
Decision timestamps, model/config versions, applied rules and quality flags from
section 7 remain future provenance work once their producer and policy are defined.

**IMPLEMENTED:** valuation -> explicit decision -> gated registration.

**NOT IMPLEMENTED:** betting acceptance policy, EV/gap/odds/freshness/kickoff/
quality thresholds, de-vig and risk/stake rules, and model-to-quote orchestration.
Synthetic approval objects in tests prove only the structural contract; they are
not evidence of a production betting strategy. Positive EV alone never creates
approval, and the gate does not reinterpret a caller's approval using an invented
threshold.

Coverage: `tests/decisions/test_pick_eligibility.py` and
`tests/use_cases/test_register_pick.py`, together with existing valuation and
registration tests. Targeted: 39 passed. Ruff: all checks passed. Full suite:
336 passed, 6 PostgreSQL integration tests skipped, 0 failed, 0 errors.
