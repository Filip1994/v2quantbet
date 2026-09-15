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
| Value decision service | Structural decision result and registration gate implemented; acceptance policy remains undefined |
| Immutable pick registration | Domain record and gated use-case implemented; full decision provenance and persistence remain incomplete |
| Quote lifecycle and closing reference | In progress |
| PostgreSQL foundation | Unit-level baseline green; six real-DB integration tests remain unexecuted |
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

## Structural decision boundary follow-up — 2026-09-15

The earlier checkpoint's missing structural boundary is now implemented:
`ValuePick -> EligibilityDecision -> register_pick() -> PickRegistration`.
Decisions are immutable and bind the exact valuation; rejected decisions carry
a machine-readable code and cannot pass the registration use-case. Registrations
created there retain the decision ID. Direct domain construction remains available
for compatibility and is not evidence that an eligibility gate was used.

There is still no betting acceptance evaluator, threshold policy, model-to-quote
orchestration, or complete decision provenance. This is a structural implementation,
not validation of any strategy or a change to Dixon-Coles mathematics. Synthetic
approval objects in tests do not establish production betting eligibility.

Verification: 39 targeted tests passed; Ruff passed; the full suite ran once,
with 336 passed, 6 PostgreSQL integration tests skipped, 0 failed and 0 errors.

## Repository implementation and verification log — 2026-09-15

The following implementation areas were audited and hardened during this pass:

- bookmaker identity policy and API-Football mapping (`8=bet365`, `11=1xBet`, `34=superbet`);
- canonical quote and quote-history validation;
- SQLite canonical quote persistence;
- PostgreSQL quote-history schema and natural-key conflict handling;
- API-Football HTTP transport error classification and retry-after parsing;
- API-Football client configuration and fixture-ID validation;
- API-Football fixture and odds payload validation;
- ingestion handling for malformed provider branches and provider-level errors.

Relevant implementation commits:

- `1a70fdee80a592669e90a1d02f431a9a1622b479`
- `c21553e01887e0f4f6692a787fe2af2d5f6ddf34`
- `a7fe3bdfd0b044e36cc2d0fd29cba9c3dab9e957`
- `099d87c8ca1c1276d015f2c5b72311b6c3167cd5`
- `5f2e430b8d390c1f21a455a4fd3af2a4062a6d2a`
- `a8e293281e66de15a4e79651dedd0f3524b4df5e`
- `ea7effabea4333c88f19b8a9dc24138f9968af02`
- `162eff83b4a04b6c0f48ef2a9afd5dcce4950bdf`
- `688b686f647aaa2c30656f14d00e0d5ae189ae25`
- `aa14730b76623e457ddc9cfa82914e9d9346ef87`
- `348ee0b22b51ea8baf6061d72b3e3f6a854e6f11`
- `b031a8afc4719f0ec3f760a8b7794787a2c376b8`
- `2db8f203fe047d2e5e807f5b6a77c966d6610432`
- `68854f11e6302220573a402d086cd96595675a67`
- `c3b24db210e719af6ba4c54372438711f9a35455`
- `2576d6da6cbda59c73cc8f895cbf7cefe9c2b27c`
- `b13c1518b922f1359762fd5ffa94206baa44c53a`
- `edcf42eae28213c442a28edb197014ae7f23321e`

### Verification status after Codex remediation

Codex independently executed the repository in a reproducible local environment and triaged the previously observed failures. The remediation was pushed through baseline commit `15ca1b5`.

- `uv run python -m ruff check .` → **All checks passed**.
- Targeted verification → **101 passed, 6 skipped**.
- Full pytest verification → **306 passed, 6 skipped, 0 failed, 0 errors**.
- The six skipped tests are the real PostgreSQL integration tests and remain unverified because no PostgreSQL service was available in that environment.
- The previous 18 failures were resolved primarily as stale tests, fixtures, and test doubles following earlier contract changes.
- One production/API-boundary defect was confirmed and fixed: `ApiFootballQuoteAdapter` now preserves `UnsupportedBookmakerError` instead of accidentally wrapping it through the broader `ValueError` handler. Production fix commit: `2e5ac1d25a8a13ed144a53f3593e2a19aaa20722`.
- The Codex remediation and documentation sequence ends at `15ca1b5`.

### Audit-side review of the remediation

The post-remediation diff was reviewed against the previous baseline. The change set is appropriately constrained: test expectations/fixtures/doubles, verification documentation, and one minimal production adapter exception-boundary fix. No evidence from this remediation justifies reopening the bookmaker mapping, canonical quote identity, quote-history natural identity, or Dixon–Coles mathematics.

`15ca1b5` is therefore accepted as the new clean non-PostgreSQL verification baseline for continuation of the audit. This label is deliberately limited: it does not claim real-PostgreSQL parity, predictive validity, calibration, profitability, or end-to-end betting eligibility correctness.

### Open verification items

1. Execute the six PostgreSQL integration tests against a real PostgreSQL 16 service when an appropriate environment is available.
2. Continue with a read-only trace of the provider-neutral production decision path: model probability → market probability → value evaluation → eligibility → pick registration.
3. Before implementing eligibility, establish from existing code/tests/docs exactly which rules are already contractual and which thresholds/policies are genuinely unspecified.
4. Do not introduce new thresholds, hardening, or mathematical changes merely to fill an unspecified design gap.
