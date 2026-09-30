# QuantLab Architecture

_Last synchronized: 2026-09-30_

## Isolation

QuantLab shares PostgreSQL infrastructure but owns separate QuantLab tables and services.

It must not write:

- Production `registered_picks`;
- Production pick decisions/value evaluations;
- Production bankroll/ledger state;
- active Production model pointers;
- Production registration policy.

## Runtime areas

`src/h2h/quantlab/` owns:

- fixture discovery/scope;
- provider/budget handling;
- market collection/classification;
- feature stores;
- model fitting/evaluation;
- shadow/canonical lab pick evidence;
- settlement;
- dashboard/analytics.

Railway runtime responsibilities are split across QuantLab web/runtime, modeler and collector services.

## GoalLab

GoalLab owns goals/BTTS research.

Current active research family:

- DC+ Pro Structural V3;
- compact V2 structural feature contract;
- chronological validation;
- exact model-hash manual authority.

Plain Production Dixon-Coles remains a read-only control reference.

## CornerLab

Current active probability source:

- Corner pressure Poisson GLM;
- historical timestamp-safe corner/pressure features;
- bookmaker prices excluded from model features;
- one complete same-book Over/Under half-line pair used for de-vig/value.

## CardLab

Current active research source:

- referee-Poisson;
- 1xBet Cards Over/Under canonical market;
- append-only event/settlement evidence.

## Discovery and data

QuantLab maintains an independent fixture universe and market/stat/context evidence.

Women's football remains globally excluded.

Feature evidence must be available no later than the decision timestamp.

## Analytics

Common metrics include:

- sample size;
- P&L / ROI;
- drawdown;
- calibration;
- Brier/log loss where applicable;
- CLV where available;
- bookmaker / league / market splits.

GoalLab and CornerLab add cross-feature Watchlist cohorts with exact-pick drilldowns.

## Governance

QuantLab has no automatic Production authority.

Owner-approved Production changes are separate, explicit changes outside the QuantLab write boundary.
