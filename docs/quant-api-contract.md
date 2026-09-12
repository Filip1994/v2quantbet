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

`DixonColesModel.fit(records, *, reference_time, xi, ridge=0.01, min_matches=80)` accepts a list of record-like objects. Each record must provide:

- `date: datetime`
- `home_id: int`
- `away_id: int`
- `home_goals: int`
- `away_goals: int`

Only records with `record.date < reference_time` are used. The quant layer expects records to represent completed matches and expects team identifiers to be stable integers. Provider-specific objects must be adapted before entering this interface.

The method returns a fitted `DixonColesModel` or raises `DixonColesFitError` if the training sample is insufficient or optimization does not converge.

## Model output

The fitted model exposes these stable attributes:

- `team_ids: tuple[int, ...]`
- `attacks: numpy.ndarray`
- `defenses: numpy.ndarray`
- `intercept: float`
- `home_advantage: float`
- `rho: float`
- `xi: float`
- `fitted_matches: int`
- `objective: float`

These attributes are model state, not a provider or persistence schema.

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

- The API/domain layer validates external payloads, provider formats, authentication, and bookmaker-specific fields.
- An adapter converts validated external data into the record shape required by `fit`.
- The quant layer performs model fitting and probability calculations.
- Persistence, transport, logging, and provider concerns remain outside the quant module.

## Compatibility rule

Changes to the public method names, required record fields, return shapes, or probability keys require dedicated tests and an explicit contract update. The golden-master tests remain the authority for numerical behavior. Public exports and the documented behavior are covered by API contract tests.