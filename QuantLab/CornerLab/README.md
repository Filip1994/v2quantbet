# CornerLab

_Last synchronized: 2026-09-30_

CornerLab owns QuantLab experiments for corner markets.

## Current model

- policy family: `CORNERLAB_PRESSURE_POISSON_POLICY_V2`
- model family: `CORNER_PRESSURE_POISSON_V1:<sha256>`
- model: **Corner pressure Poisson GLM**
- feature version: `CORNER_PRESSURE_FEATURES_V1`

The model predicts full-match total corners and converts the expected count into Over/Under probabilities through a Poisson distribution.

Bookmaker prices are not model features.

## Feature family

Timestamp-safe rolling features include:

- corners for/against;
- possession;
- total shots;
- shots on target;
- blocked shots;
- inside-box shots;
- offsides;
- passing/accuracy;
- venue-specific histories;
- short-vs-long window trend signals.

Missing provider statistics remain missing and are imputed from the training sample during fitting; they are not silently converted to zero.

## Training

- chronological history;
- only earlier matches can create a target feature;
- minimum prior team history;
- standardized numeric features;
- ridge-regularized Poisson GLM;
- immutable model artifact and target feature snapshot.

## Market

Current supported betting family is conservative:

- full-match total corners;
- complete same-book Over/Under pair;
- half-lines only;
- no team totals/halves/handicap/race/exact/range variants.

Bet365 and 1xBet may both provide eligible pairs.

## Current bottleneck

The main current bottleneck is **team-history/statistics coverage**, not the raw model training-sample size.

Do not weaken quality gates simply to create more picks.

Historical bookmaker-aligned calibration/evaluation remains a priority before any broader authority discussion.

## Model diagnostics

Track:

- MAE / RMSE;
- observed vs predicted means;
- variance-to-mean;
- Pearson dispersion;
- Poisson log likelihood;
- line-level calibration/Brier/log loss.

If dispersion remains materially above Poisson expectations, evaluate Negative Binomial as a measured alternative.

## Analytics

CornerLab Analytics starts with **Watchlist · ROI discovery**:

- Model-line gap × price;
- Pressure trend × matchup;
- Model vs market × price;
- Reliability × market.

Rows drill down to exact settled picks.

## Production boundary

CornerLab is shadow/research-only. Any Production use requires explicit owner approval and a separate Production implementation.
