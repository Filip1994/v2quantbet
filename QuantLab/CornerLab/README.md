# CornerLab

CornerLab owns QuantLab experiments for corner markets.

## Active model — V2 pressure Poisson

CornerLab V2 replaces the cross-book fair-reference model as the active corner probability
source.

Policy:

- `CORNERLAB_PRESSURE_POISSON_POLICY_V2`

Model family:

- `CORNER_PRESSURE_POISSON_V1:<sha256>`
- model name: **Corner pressure Poisson GLM**
- feature version: `CORNER_PRESSURE_FEATURES_V1`

The model predicts the expected **full-match total number of corners** and converts that
mean into Over/Under probabilities with a Poisson distribution.

Bookmaker prices are **not** model inputs.

## Structural feature family

For both home and away teams the model uses rolling, timestamp-safe historical match
statistics.

### Recent all-match windows

Last-5:

- corners for
- corners against
- ball possession
- total shots for
- total shots against
- shots on target for
- shots on target against
- blocked shots
- shots inside the box
- offsides
- accurate passes
- pass accuracy

Last-10:

- corners for
- corners against
- ball possession
- total shots
- shots on target

### Venue windows

Last-5 home/away-specific:

- corners for
- corners against
- possession
- total shots
- shots on target
- shots inside the box
- accurate passes

The initial feature registry therefore captures both direct corner production and the
attacking-pressure process that tends to generate corners.

Missing historical stat fields are explicit missing values. During model fitting they are
imputed from the training-sample feature mean; missingness is never coerced to zero.

## Training

The model is fitted once per QuantLab decision cycle.

Training rules:

1. historical matches are processed in kickoff order;
2. a training target can use only matches that occurred earlier in that ordered history;
3. each target team needs at least three prior statistical matches;
4. at least 80 training examples are required;
5. numeric features are standardized;
6. a ridge-regularized Poisson GLM learns the coefficients;
7. no hand-written football feature weight is promoted into the probability model.

The fitted artifact persists:

- model version
- training cutoff
- sample size
- history match count
- ridge penalty
- coefficients
- feature means
- feature scales
- fitting metadata

Target fixture snapshots persist the exact input feature vector and expected total corners.

## Research scope

CornerLab uses `CARDCORNER_MARKET_DRIVEN_V4`.

There is no domestic league allowlist. Women's football is globally hard-blocked; the
remaining discovered universe retains CORNER markets wherever the provider publishes them.

Historical `/fixtures/statistics` acquisition is also broad. Before spending a
fixture-statistics request, CornerLab caches API-Football's league/season
`coverage.fixtures.statistics_fixtures` capability. A provider-declared `false`
temporarily blocks fixture-statistics spend for that league/season; `true` is only a
capability signal and never guarantees that every match has statistics. Missing coverage
remains UNKNOWN and does not fabricate an unsupported result.

A fixture response that does not contain both teams is still stored as an append-only
`UNAVAILABLE` statistics-capture watermark so the same fixture-level miss is not
re-requested every cycle.

## Supported betting market

V2 currently supports only conservative full-match total-corner markets:

- owner = CORNER
- one complete OVER/UNDER pair from the same bookmaker/capture
- half-line only (`x.5`)
- no team totals
- no halves
- no handicap / Asian handicap
- no race/exact/range/odd-even variants

**Only one bookmaker is required.**

Bet365 and 1xBet are both eligible sources, but they no longer need to quote the same line.
The model probability comes from CornerLab V2; the selected bookmaker pair is only used
to calculate the de-vig market probability, edge and EV.

## Shadow value policy

A V2 PICK requires:

- edge >= 3 percentage points
- EV >= 3%
- odds 1.40–4.00
- quote age <= 13 hours
- at least 15 minutes to kickoff

For one line, if multiple books/directions qualify, only the highest-EV candidate becomes
PICK. Other qualifying candidates are PASS / `BETTER_VALUE_AVAILABLE`.

Everything remains shadow-only. CornerLab does not write production registered picks,
production model state or bankroll state.

## V1 historical baseline

Task 003 originally used `CROSS_BOOK_FAIR_REFERENCE_V1`, where the other bookmaker's
de-vig price acted as a reference probability.

That V1 path remains useful as historical benchmark evidence, but it is no longer the
active CornerLab probability source after V2.
