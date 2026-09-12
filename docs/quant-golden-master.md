# Quant Golden-Master Baseline

## Purpose

Freeze the legacy quantitative baseline before any V2 quant implementation changes it.
This document is a reference lock, not a claim that the V2 implementation is complete.

## Legacy reference

- Repository: `Filip1994/h2h`
- Reference commit: `9b2337b8432546420945f32586b7a4b84355589b`

## Frozen mathematical sources

| Component | Legacy path | Blob SHA |
| --- | --- | --- |
| Dixon-Coles model | `src/quantbot/dixon_coles.py` | `67c2f7b70f6e4fbe67c4c7fa5bafc85f0b93ce66` |
| Probability calibration | `src/quantbot/calibration.py` | `e88e08b24b0432adf50b82ec8f55b8710830155a` |
| Quant engine orchestration | `src/quantbot/engine.py` | `see reference commit above` |

## Existing legacy regression anchors

The legacy test suite contains deterministic anchors for the Dixon-Coles implementation:

- `dixon_coles_tau(0, 0, 1.4, 1.1, -0.05) == 1.077`
- `dixon_coles_tau(2, 1, 1.4, 1.1, -0.05) == 1.0`
- synthetic training data is used to verify coherent market probabilities
- OVER_25 + UNDER_25 must equal 1.0 within test tolerance
- fitted attack and defense vectors must sum to zero within `1e-10`
- `rho` must remain within `[-0.20, 0.20]`

These anchors are taken from the legacy test file `tests/test_dixon_coles.py` at the same reference commit.

## C2 executable fixture

The V2 repository now contains `tests/quant/test_dixon_coles_golden_master.py`.
It builds a deterministic six-team, ten-round synthetic dataset containing 300 matches and
asserts the locked legacy-reference outputs for:

- fitted match and team counts;
- objective, intercept, home advantage, and `rho`;
- attack and defense parameter vectors;
- expected goals for a fixed fixture;
- OVER 2.5, UNDER 2.5, and BTTS YES probabilities;
- low-score Dixon–Coles correction values.

The fixture is synthetic and deterministic. It is intended to detect unintended numerical
or behavioral drift, not to represent historical football data. The regression tolerances are
explicitly bounded at `1e-6` for floating-point outputs.

## Freeze rule

Until executable V2 golden-master tests are established, do not change the mathematical behavior of:

- Dixon-Coles fitting
- time decay
- ridge regularization
- expected-goals calculation
- score-matrix construction
- low-score Dixon-Coles correction
- market probability derivation
- Platt calibration
- calibration acceptance metrics
- probability haircut / pricing inputs
- EV and edge calculations
- risk mathematics

Infrastructure may be redesigned around these components, but mathematical behavior must be demonstrated equivalent before being changed.

## C1 boundary

C1 establishes the immutable legacy reference and regression anchors.
It does **not** yet claim that V2 reproduces the full legacy model. That executable equivalence is a later C-task and must be proven with tests before the quant layer is considered frozen.

## C2 boundary

C2 establishes the first executable V2 golden-master regression boundary. It does not authorize
changes to quant mathematics; subsequent changes must preserve these tests or update the locked
reference through an explicit, reviewed baseline change.
