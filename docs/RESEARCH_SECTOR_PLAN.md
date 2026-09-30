# QuantBet — Research Sector Plan

_Last synchronized: 2026-09-30_

## Purpose

Research is the analytical layer of QuantBet. It explains and compares signals; it does not directly register, skip, stake, settle or otherwise mutate Production.

Central questions:

- where is the model calibrated;
- where do price/model/value structures repeat;
- what does CLV say before enough realized ROI exists;
- how stable are results across time, leagues and bookmakers;
- which rules deserve owner review.

## Canonical dataset

Research uses the comparable final-gate decision universe.

Routes:

- `PLAYED`;
- `SKIPPED`;
- `BLOCKED_EXPOSURE`.

Rows that fail earlier edge/EV/odds/freshness/timing/model gates belong to lower-level diagnostics, not the same final-gate cohort.

Research preserves raw values in addition to bucket labels.

## Current analyses

The active analytics layer supports:

- model probability buckets;
- market fair probability buckets;
- EV buckets;
- odds buckets;
- market / selection;
- route;
- bookmaker;
- league;
- quote freshness;
- model/policy/devig regimes;
- time slices;
- ROI/P&L;
- win rate / expected win rate / calibration gap;
- Wilson win-rate intervals;
- CLV coverage / average / median / positive rate.

## Methodological controls

Always guard against:

- look-ahead leakage;
- target leakage;
- stale/duplicate quotes;
- selection bias;
- missing-data bias;
- bookmaker availability bias;
- multiple testing;
- overfitting;
- temporal and league/regime drift.

Chronological/walk-forward evaluation remains preferred when evaluating model changes.

## Production governance

### No automatic promotion

No Research result can modify Production by itself.

### Owner approval

For bucket-based Production selection, explicit owner approval is the authority boundary.

Forward/OOS confirmation is valuable evidence but **not a mandatory gate** if the owner deliberately approves the bucket.

### Bans

Do not permanently ban a bucket because of a short negative run.

Default performance-based ban review horizon: **3–6 months**.

Immediate suspension is appropriate for technical-integrity failures such as leakage, wrong settlement, identity corruption, bad quote alignment or model/data bugs.

## Output requirements

Every important research view/result should make clear:

- data period;
- settled N;
- exact cohort definition;
- model/policy regime;
- ROI/P&L;
- calibration evidence;
- CLV evidence;
- important data-quality limitations.

## Separation from QuantLab

Research analyzes the Production-comparable final-gate universe.

QuantLab is a separate model laboratory with broader multi-market data/model experimentation. The two can share analytical principles without sharing write authority.
