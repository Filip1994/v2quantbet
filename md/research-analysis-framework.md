# QuantBet Research Analysis Framework

_Last updated: 2026-09-30_

This document defines the current Research universe, bucket semantics, analytics metrics and Production-governance boundary.

## 1. Core principle

Research is a read-only analytical superset of comparable Production candidates.

Production is not a separate “better” sample. Research must preserve enough context to compare what was played, skipped or blocked only by exposure.

## 2. Canonical row

Research uses one canonical candidate per fixture at the common research decision stage.

For Production picks that later pass final quote verification/repricing, Research retains the comparable preliminary decision-stage evidence rather than mixing later Production pricing with earlier exposure-blocked pricing.

## 3. Routes

| Route | Meaning |
|---|---|
| `PLAYED` | Registered Production candidate treated as played/effective for operator tracking. |
| `SKIPPED` | Registered Production candidate later explicitly skipped. |
| `BLOCKED_EXPOSURE` | Candidate passed the relevant final-gate logic and was blocked by open exposure. |

Earlier failures remain available in lower-level diagnostics but are not mixed into this final-gate universe.

## 4. Core stored evidence

Preserve:

- fixture / competition / kickoff;
- market / selection;
- bookmaker/source;
- entry odds;
- model probability;
- market fair probability;
- edge;
- EV;
- quote observed/captured timestamps;
- model version;
- prediction/devig/policy fingerprints;
- route;
- Production pick ID where applicable;
- settlement/result;
- closing odds and same-book CLV where valid.

## 5. Bucket dimensions

Current analytics include:

### Model probability

`40–45%`, `45–50%`, `50–55%`, `55–60%`, `60–65%`, `65–70%`, `70–75%`, `75%+`.

### Market fair probability

`<25%`, `25–35%`, `35–40%`, `40–45%`, `45–50%`, `50–55%`, `55–60%`, `60–65%`, `65–75%`, `75%+`.

### EV

`7–10%`, `10–15%`, `15–20%`, `20–30%`, `30%+` for the current Production-comparable policy range, while raw EV remains stored.

### Odds

`1.40–1.60`, `1.61–1.80`, `1.81–2.00`, `2.01–2.50`, `2.51–3.00`, `3.01–3.50`, `other`.

Additional dimensions include market, selection, route, bookmaker, league, freshness, time and immutable model/policy regimes.

## 6. Metrics

Cohort tables should prefer evidence density over one headline ROI number.

Current core metrics:

- N / graded N;
- wins / losses / voids;
- win rate;
- expected win rate;
- calibration gap;
- Wilson 95% win-rate interval;
- flat P&L;
- flat ROI;
- average odds;
- average model probability;
- average market fair probability;
- average edge / EV;
- CLV count / coverage;
- average / median CLV;
- positive-CLV rate.

Priority enhancement: add ROI uncertainty, preferably fixture-level bootstrap.

## 7. Evidence bands

Current descriptive bands:

- `<20`: `SIGNAL_ONLY`;
- `20–49`: `MONITOR`;
- `50–99`: `PROVISIONAL_EVIDENCE`;
- `100+`: `STABILITY_REVIEW`.

These labels describe sample maturity. They do not carry Production authority.

## 8. Watchlist / bucket discovery

Watchlists are for fast pattern discovery and exact-pick drilldown.

Important distinction:

- a strong historical bucket is evidence;
- it is not an automatic Production rule;
- it is also not required to wait for a fixed forward/OOS sample before the owner may approve it.

When a bucket is owner-approved, preserve its exact rule/version so later performance can be evaluated against the decision that was actually made.

## 9. Production promotion

Production promotion requires an explicit owner decision.

Forward/OOS evidence should be shown separately when available and is useful for confidence, but it is **advisory rather than a mandatory gate**.

No analytics endpoint may register or alter Production picks automatically.

## 10. Production bucket review / ban

A weak period should normally move a bucket to human `UNDER_REVIEW`, not directly to a ban.

Default permanent performance-ban horizon: **3–6 months**.

Review together:

- N;
- ROI;
- CLV;
- calibration;
- odds mix;
- league/bookmaker breadth;
- time/regime stability.

Immediate suspension is reserved for technical-integrity problems.

## 11. Time and regime analysis

Always distinguish:

- discovery/history;
- post-approval Production behavior;
- model/policy changes;
- league/bookmaker shifts.

A bucket that spans incompatible regimes should not be treated as one homogeneous sample without an explicit combined view.

## 12. Data-integrity rules

- Research never blocks Production writes.
- Research settlement never creates fake Production settlement/bankroll events.
- Raw values remain stored when buckets are added.
- Historical backfills are deterministic.
- Bucket definitions and model/policy versions must be auditable.
- Same-book closing methodology remains preferred for CLV.
- Exposure route is path-dependent and not a model-quality label.

## 13. Open analytical priorities

- ROI uncertainty/bootstrap;
- 30/60/90-day stability;
- league/bookmaker breadth indicators;
- coverage/dropout funnels;
- clearer discovery-vs-post-approval comparison;
- model/policy regime stability;
- continued exact-pick drilldowns.

See [../docs/CURRENT_PRIORITIES.md](../docs/CURRENT_PRIORITIES.md).
