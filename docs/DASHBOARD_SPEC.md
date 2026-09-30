# QuantBet — Dashboard Specification

_Last synchronized: 2026-09-30_

## 1. Dashboard families

QuantBet has three different dashboard concerns:

1. **Production dashboard** — operational picks, prices, operator state, settlement, bankroll and worker health.
2. **Research dashboard** — read-only final-gate candidate analysis.
3. **QuantLab dashboard/analytics** — isolated GoalLab/CornerLab/CardLab operational and research views.

Do not collapse these into one write-authority surface.

## 2. Production dashboard

Production dashboard facts come from PostgreSQL.

Important pick fields:

- fixture / competition / kickoff;
- market / selection;
- registered bookmaker;
- Pick odds;
- same-book current odds;
- best current odds where available;
- same-book closing odds;
- model probability;
- de-vig market probability;
- edge / EV;
- model/policy provenance;
- result / settlement / P&L / CLV;
- operator state.

Operator state events are append-only. The domain currently supports derived `PENDING` plus explicit `PLAYED` / `SKIPPED` events. Effective risk excludes `SKIPPED` while preserving immutable reservation/history evidence.

Production is the only dashboard family with the authenticated operator-state write path.

## 3. Research dashboard

Research is read-only.

Required views:

- Active / awaiting / settled history as applicable;
- PLAYED / SKIPPED / BLOCKED_EXPOSURE route filters;
- model/market probability, EV and odds buckets;
- market / selection / league / bookmaker / freshness;
- model/policy regime;
- N, ROI, calibration and CLV;
- exact cohort drilldown to underlying picks.

## 4. QuantLab dashboard

QuantLab is read-only with respect to user HTTP actions.

Operational pages show active/settled lab picks.

Analytics pages show:

- time-window metrics;
- model/market/selection/league/bookmaker breakdowns;
- calibration;
- ROI/P&L/drawdown;
- feature-derived buckets;
- exact bucket drilldowns.

GoalLab and CornerLab must show **Watchlist · ROI discovery** before the broader analytics tables.

Headers in analytics tables are sortable.

## 5. Integrity rules

The UI must not:

- fabricate closing odds;
- recompute or rewrite historical decision facts;
- treat a missing value as zero;
- hide model/policy regime changes;
- automatically change Production selection policy from an analytics result.

## 6. Release/health view

Add or retain:

- worker heartbeats;
- stale/failure state;
- provider budget;
- model coverage/failures;
- deployed SHA;
- deployment timestamp;
- CI state for deployed SHA where practical.

## 7. Governance display

For important research buckets, show enough context to support owner decisions.

Future/OOS evidence may be shown, but it must not be presented as a mandatory approval requirement.

Performance-based bans should be treated as deliberate 3–6 month review decisions unless a technical-integrity failure requires immediate suspension.
