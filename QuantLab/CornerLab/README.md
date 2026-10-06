# CornerLab

CornerLab owns QuantLab experiments for corner markets.

## Active model — V2 pressure Poisson

CornerLab V2 replaces the cross-book fair-reference model as the active corner probability
source.

Policy:

- `CORNERLAB_PRESSURE_POISSON_POLICY_V3`

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

Historical `/fixtures/statistics` acquisition is also broad. A provider response that
does not contain both fixture teams is stored as an append-only
`UNAVAILABLE` statistics-capture watermark so the same unsupported fixture is not
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

A V3 PICK requires:

- edge >= 3 percentage points
- EV >= 3%
- odds 1.40–4.00
- quote age <= 13 hours
- at least 15 minutes to kickoff

CornerLab emits at most **one canonical PICK per fixture**. All qualifying lines,
directions and bookmakers are ranked fixture-wide by:

1. expected value (descending);
2. edge (descending);
3. odds (descending);
4. deterministic tie-breakers only.

The highest-ranked candidate becomes PICK / `CANONICAL_FIXTURE_VALUE_PICK`.
Every other qualifying candidate remains in the decision ledger as
PASS / `BETTER_FIXTURE_VALUE_AVAILABLE`.

If a CornerLab shadow bet already exists for the fixture, later refresh cycles cannot
create another exposure; newly qualifying alternatives are recorded as
PASS / `FIXTURE_PICK_ALREADY_EXISTS`. Historical pre-V3 multi-pick rows are preserved
as immutable research evidence.

Everything remains shadow-only. CornerLab does not write production registered picks,
production model state or bankroll state.

## Dashboard and analytics

CornerLab follows the same operational split as GoalLab.

The QuantLab **Dashboard** shows only active CornerLab picks and settled pick history
(WIN / LOSS / VOID), with the core entry odds, probability, edge, EV and P/L fields.

The separate **Analytics** tab evaluates the settled CornerLab ledger with:

- 7-day, 30-day and lifetime performance;
- market/selection, league, bookmaker and model-version breakdowns;
- win rate, ROI and max drawdown;
- Brier score, binary log loss and calibration bins.

The structural feature/model context remains in the underlying research system; it is no
longer mixed into the operational homepage.

## V1 historical baseline

Task 003 originally used `CROSS_BOOK_FAIR_REFERENCE_V1`, where the other bookmaker's
de-vig price acted as a reference probability.

That V1 path remains useful as historical benchmark evidence, but it is no longer the
active CornerLab probability source after V2.
