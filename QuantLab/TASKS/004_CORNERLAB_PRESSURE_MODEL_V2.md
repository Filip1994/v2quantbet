# Task 004 — CornerLab V2 Pressure Statistics Model

Status: implementation branch.

## Objective

Replace CornerLab's cross-book reference probability with an independently trained
structural corner model.

The model must use historical attacking/territorial statistics in addition to direct corner
form and must not assign arbitrary hand-written coefficients.

## Data acquisition

Expand `quantlab_match_statistics_observations` to retain:

- corner kicks
- ball possession
- shots on goal
- shots off goal
- total shots
- blocked shots
- shots inside box
- shots outside box
- offsides
- goalkeeper saves
- total passes
- accurate passes
- pass accuracy

Existing foul/card fields remain.

Add `quantlab_statistics_captures` so successful and structurally unavailable statistics
responses are both durably watermarked.

A response missing either fixture team is `UNAVAILABLE`, not a retry-every-cycle error.

## Model

Feature version: `CORNER_PRESSURE_FEATURES_V1`.

Model: ridge-regularized Poisson GLM over total full-match corners.

Structural features use last-5, last-10 and venue-specific history for:

- direct corners for/against;
- possession;
- shot volume and shots on target;
- shots conceded;
- blocked and inside-box shots;
- offsides;
- passing volume/accuracy.

Minimum team history: 3 matches.

Minimum fitted training examples: 80.

The model is trained once per decision timestamp/cycle and reused for all target fixtures in
that cycle.

Bookmaker prices are excluded from model fitting.

## Market evaluation

Supported V2 market:

- full-match Total Corners
- complete two-way Over/Under quote
- half-lines only

One bookmaker is sufficient.

Market fair probability uses proportional two-way de-vig on the selected bookmaker's
Over/Under pair.

Model probability uses the Poisson distribution implied by the fitted expected total
corners.

Value gates remain:

- edge >= 3pp
- EV >= 3%
- odds 1.40–4.00
- quote <= 13h old
- >= 15m to kickoff

## Audit

Migration 032 adds:

- expanded pressure fields to `quantlab_match_statistics_observations`;
- `quantlab_statistics_captures`;
- `quantlab_corner_model_versions`;
- `quantlab_corner_feature_snapshots`;
- a relaxed CornerLab PICK evidence constraint so a second bookmaker is not mandatory.

The following are persisted for reproducibility:

- model coefficients;
- means/scales;
- training cutoff and sample size;
- target raw/imputed feature vector;
- expected total corners;
- exact market observation pair;
- market/model probabilities;
- edge / EV;
- policy/model versions.

## Isolation

Task 004 remains QuantLab-only.

No writes to:

- production model activation;
- registered_picks;
- production pick decisions;
- bankroll;
- staking/accounting.
