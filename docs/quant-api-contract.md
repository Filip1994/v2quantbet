# Quant API Contract

## Scope

This document defines the public contract of the Dixon–Coles quant layer. It does not change the model mathematics or introduce bookmaker-specific structures.

## Canonical implementation

The canonical implementation is `h2h.quant.dixon_coles.DixonColesModel`.

The public package `h2h.quant` exports:

- `DixonColesModel`;
- `DixonColesFitError`, raised when fitting or prediction cannot produce a valid result;
- `dixon_coles_tau`, the low-score Dixon–Coles correction function.

The package exports are aliases of the canonical module objects.

## Training input

`DixonColesModel.fit(records, *, team_id_namespace, reference_time, xi, ridge=0.01, min_matches=80)` accepts a list of record-like objects. Each record must provide:

- `date: datetime`
- `home_id: int`
- `away_id: int`
- `home_goals: int`
- `away_goals: int`

Only records with `record.date < reference_time` are used. The quant layer expects records to represent completed matches and expects team identifiers to be stable integers. Provider-specific objects must be adapted before entering this interface.

`team_id_namespace` is a required nonblank string retained by the fitted model. On this low-level mathematical API it remains the caller's explicit claim about the namespace shared by every training-record team ID. Production API-Football callers instead construct acquisition with `build_trusted_api_football_historical_results(settings)` and use `fit_api_football_dixon_coles()`. The factory fixes the canonical endpoint and approved production HTTP transport without caller injection; the bridge accepts only the internally minted dataset and derives `api-football`, so the caller cannot select the namespace at that boundary. General injected clients and caller-normalized records do not carry that authority.

`Fixture.provider_home_team_id` and `Fixture.provider_away_team_id` retain ordered, provider-qualified identifiers from fixture discovery. They may be used as Dixon–Coles `home_id` and `away_id` only when the fitted training records are explicitly known to use the same provider namespace. Their presence alone does not prove that namespace association, and the quant layer does not perform provider-team entity resolution.

The method returns a fitted `DixonColesModel` or raises `DixonColesFitError` if the training sample is insufficient or optimization does not converge.

## Model output

The fitted model exposes these stable attributes:

- `team_ids: tuple[int, ...]`
- `team_id_namespace: str`
- `attacks: numpy.ndarray`
- `defenses: numpy.ndarray`
- `intercept: float`
- `home_advantage: float`
- `rho: float`
- `xi: float`
- `fitted_matches: int`
- `objective: float`

These attributes are model state, not a provider or persistence schema.

## Production-facing fixture prediction

Low-level numerical methods remain available for model tests and internal calculation. Production-facing fixture execution uses `DixonColesFixturePredictor.predict(fixture, *, max_goals=10)`.

The predictor derives an internal immutable target from the authoritative `Fixture` and exposes it through the read-only `PredictionTarget` interface. The target reuses `ResolvedFixtureIdentity`, retains ordered provider home/away team IDs, and derives their namespace from the provider fixture reference. Construction fails when provider fixture identity or either provider team ID is missing, when the home and away IDs are equal, or when canonical and provider fixture identity contradict one another. `PredictionTarget` has no supported public constructor or factory.

Before invoking `market_probabilities()`, the predictor requires the model's `team_id_namespace` to equal the target's team-ID namespace. It then passes the target home ID as home and target away ID as away. The returned read-only `FixturePrediction` interface is backed by an internal immutable result that retains that exact execution target and a defensive, read-only copy of the produced probabilities. Neither the target interface nor the result interface is publicly constructible, and the predictor has no fixture-ID override argument.

`evaluate_prediction_quote(prediction, quote)` is the identity-safe valuation gateway. It accepts only the internal result form produced by `DixonColesFixturePredictor`, then requires exact canonical fixture-ID equality before delegating selection mapping to `model_probability_for_selection()` and numerical valuation to unchanged `evaluate_value()`. Supported public APIs therefore cannot rebind arbitrary or fixture-A probabilities to a fixture-B target. Raw provider IDs and canonical IDs are not interchangeable, and cross-provider equivalence is never inferred. This supported-API boundary does not attempt to defend against deliberate private-module imports or reflection.

The target-binding boundary composes with the implemented FT-only API-Football historical acquisition and provenance-aware fitting bridge. Model artifact/version lifecycle, scheduled training and durable prediction provenance are not implemented.

## Prediction methods

### `expected_goals(home_id, away_id)`

Returns `(lambda_home, lambda_away)` as a tuple of finite positive floats. Both team IDs must exist in the fitted training sample; otherwise `DixonColesFitError` is raised.

### `score_matrix(home_id, away_id, max_goals=10)`

Returns a two-dimensional NumPy array with shape `(max_goals + 1, max_goals + 1)`. Entries are non-negative probabilities and the matrix is normalized to sum to one. Invalid or non-positive `max_goals` values are outside the current contract and must be rejected by the caller until an explicit validation policy is introduced.

### `market_probabilities(home_id, away_id, max_goals=10)`

Returns a dictionary containing:

- `OVER_2_5`
- `UNDER_2_5`
- `BTTS_YES`

Each value is a finite probability in `[0, 1]`. The over/under values are complementary within floating-point tolerance.

### `team_match_counts(records)`

A static helper returning `Counter[int]`, counting every appearance of each team as either home or away. It does not apply the `reference_time` filter and does not fit a model.

## Responsibility boundary

### Canonical selection bridge

`h2h.quant.market_probability.model_probability_for_selection(probabilities, *,
market, selection) -> float` selects the probability for canonical `Market` and
`Selection` enum instances:

| Canonical pair | Consumed model probability |
| --- | --- |
| `OU_25 / OVER` | `OVER_2_5` |
| `OU_25 / UNDER` | `UNDER_2_5` |
| `BTTS / YES` | `BTTS_YES` |
| `BTTS / NO` | `1.0 - BTTS_YES` |

BTTS NO is bridge-derived under the normalized model probability contract, not a
new Dixon-Coles output key. Model mathematics and the three public output keys
remain unchanged. The bridge is imported from its own module; existing package
exports remain unchanged.

The input must be a `collections.abc.Mapping`. Only the consumed scalar is checked:
it must be a `numbers.Real` other than bool, finite and in `[0, 1]`. Integers at the
endpoints and real numeric scalars are accepted and the result is a Python float.
No string coercion, clipping, rounding, renormalization or missing-value fallback
is performed. Input is not mutated; unrelated keys need not be present or valid.

Wrong input/enum/scalar types raise `TypeError`. Unsupported canonical pairs,
missing required keys, non-finite or out-of-range probabilities raise `ValueError`.
There is no new exception hierarchy. BTTS NO validates YES before complementing it.

The caller must associate the model output with the quote's correct fixture and
home/away teams. The mapping contains no fixture identity and cannot prove this
association. This bridge performs no odds evaluation, acceptance, de-vig,
bookmaker filtering, risk/stake calculation, eligibility, registration or publication.

Tests: `tests/quant/test_market_probability.py` covers mappings/errors, a hand-set
normalized matrix through the existing `score_matrix` seam, and all four mappings
composed with `evaluate_value()`. The composition fixture isolates aggregation;
it does not fit a model or establish predictive validity, calibration, profitability
or betting edge.

### Existing layer responsibilities

- The API/domain layer validates external payloads, provider formats, authentication, and bookmaker-specific fields.
- An adapter converts validated external data into the record shape required by `fit`.
- The quant layer performs model fitting and probability calculations.
- Persistence, transport, logging, and provider concerns remain outside the quant module.

## Compatibility rule

Changes to the public method names, required record fields, return shapes, or probability keys require dedicated tests and an explicit contract update. The golden-master tests remain the authority for numerical behavior. Public exports and the documented behavior are covered by API contract tests.
