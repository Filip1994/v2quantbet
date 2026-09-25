# QuantBet Research Analysis Framework

_Last updated: 2026-09-25_

This document defines the research dataset, current bucketization, cohort semantics, derived metrics, and the intended workflow for making future Production more selective without contaminating the research sample.

## 1. Core principle

Research is the superset of Production.

A fixture enters the Research universe when its canonical candidate reaches the final production-eligibility boundary. Research must contain both:

- candidates that become real-money Production picks;
- candidates that would otherwise be Production-eligible but are rejected only because the open-exposure cap is full.

The purpose is to build one comparable dataset from which future Production filters can be learned. Production must not be treated as a separate "better" sample.

Research remains read-only and must never change registration, bankroll, exposure, staking, settlement, model training, calibration, or any other Production behavior.

## 2. Canonical unit

Research uses exactly one canonical pick per fixture.

The canonical row is the candidate used at the common research decision stage. For Production picks that later go through final-quote verification/repricing, Research uses the original preliminary candidate evaluation so that Production and exposure-blocked cohorts are compared at the same stage.

This avoids comparing:

- a Production pick at a later repriced quote;
- against an exposure-blocked pick at an earlier preliminary quote.

Historical data is also projected to one research row per fixture.

## 3. Research dispositions / routes

Every Research row belongs to one of these routes:

| Disposition | Meaning |
|---|---|
| `PLAYED` | Candidate registered in Production and left as played. |
| `SKIPPED` | Candidate registered in Production but later manually skipped. |
| `BLOCKED_EXPOSURE` | Candidate passed the relevant gates and the sole preliminary rejection was `MAX_OPEN_EXPOSURE_EXCEEDED`. |

Important: candidates rejected for other reasons are not part of this Research universe. Raw `value_evaluations` remain available for deeper model diagnostics, but they are a different dataset.

Examples of candidates that should **not** be mixed into the final-gate Research universe include rows failing edge, EV, odds, timing, freshness, or other eligibility checks.

## 4. Current Production settings — do not infer quality from these

Current fixed Production settings remain independent from Research:

- minimum edge: **7%**
- minimum expected value: **7%**
- fixed stake: **300 RSD**
- maximum PLAYED/open exposure: **3,000 RSD**
- Kelly staking: **not enabled**
- Production default state: **PLAYED**
- manual `SKIPPED` picks remain audit/history and do not consume the hard exposure cap

These values are not evidence that the corresponding region is optimal. They are the current operating policy while data is accumulated.

## 5. Current Research buckets

### 5.1 Model probability buckets

These buckets use the model probability, not market probability:

- `40–45%`
- `45–50%`
- `50–55%`
- `55–60%`
- `60–65%`
- `65–70%`
- `70–75%`
- `75%+`

### 5.2 Expected-value buckets

- `7–10%`
- `10–15%`
- `15–20%`
- `20–30%`
- `30%+`

### 5.3 Odds buckets

- `1.40–1.60`
- `1.61–1.80`
- `1.81–2.00`
- `2.01–2.50`
- `2.51–3.00`
- `3.01–3.50`
- `other`

### 5.4 Market fair probability buckets — TODO

Market fair probability is currently stored/displayed but is **not yet bucketed**.

It should be added as a separate analytical dimension. The exact bucket boundaries should be chosen before implementation and then kept stable long enough to accumulate comparable data.

Do not confuse:

- **model probability** — our estimated event probability;
- **market fair probability** — de-vigged / fair probability implied by the market.

The difference between them contributes to measured edge, but they should also be analyzed separately.

## 6. Markets currently covered

Research counterfactual settlement currently supports:

- `OU_25`
- `BTTS`

Market and selection must always be retained as analysis dimensions because performance can differ materially across markets even when model probability or EV is similar.

## 7. Research entry data to preserve

For each canonical research candidate, preserve enough information to reproduce the decision context:

- fixture identity;
- league / competition;
- kickoff;
- market;
- selection;
- model probability;
- market fair probability;
- entry odds;
- edge;
- expected value;
- bookmaker;
- source;
- quote observation/capture timestamps;
- quote age / freshness classification;
- probability bucket;
- EV bucket;
- odds bucket;
- research qualification timestamp;
- disposition / route;
- Production pick ID where applicable;
- exposure metadata for exposure-blocked candidates.

Future market-probability bucket should be derived from the stored market fair probability rather than replacing the raw value.

## 8. Outcomes and comparison basis

Research outcome is counterfactual and normalized to a flat stake.

Current comparison stake:

- **300 RSD flat stake**

For a Production pick, keep these concepts separate:

1. **actual Production result / bankroll effect**;
2. **Research flat-stake P/L** used for cohort comparison.

This makes `PLAYED`, `SKIPPED`, and `BLOCKED_EXPOSURE` directly comparable even if Production staking changes later.

## 9. Closing odds and CLV

Research closing odds use the later stored quote from the same series/source before kickoff.

Research CLV is only considered available when the closing observation is later than the Research entry observation.

CLV should be analyzed together with realized ROI, not as a substitute for it.

Useful CLV views:

- average CLV;
- median CLV;
- positive-CLV rate;
- CLV distribution by bucket;
- CLV by market;
- CLV by bookmaker;
- CLV by route.

## 10. Minimum metrics for later analysis

Every analysis table should show the sample size `N`. Never interpret win rate or ROI without `N`.

At minimum, evaluate:

- settled count;
- wins / losses / voids;
- win rate;
- expected win rate from model probabilities;
- calibration gap;
- flat-stake P/L;
- flat-stake ROI;
- average entry odds;
- average model probability;
- average market fair probability;
- average edge;
- average EV;
- average CLV;
- median CLV;
- positive-CLV rate.

For calibration, later analysis should compare predicted probability against realized frequency, preferably with confidence intervals rather than only point estimates.

## 11. Primary analysis dimensions

The main analytical cube should support combinations of:

- model probability bucket;
- market fair probability bucket — once added;
- EV bucket;
- odds bucket;
- market;
- selection;
- disposition;
- bookmaker;
- league / competition;
- quote freshness;
- time-to-kickoff / registration window.

The central future question is not "did Research win?" but:

> In which stable regions of the decision space do we observe repeatable calibration, ROI, and/or CLV strong enough to justify stricter Production selection?

## 12. Production vs Research analysis

Production should be treated as a route inside the same Research universe, not as an independent quality sample.

Useful comparisons:

- `PLAYED` vs `BLOCKED_EXPOSURE`;
- `PLAYED` vs `SKIPPED`;
- all routes combined;
- bucket-level performance independent of route.

Exposure is path-dependent. Therefore, differences between `PLAYED` and `BLOCKED_EXPOSURE` must not automatically be interpreted as model-quality differences.

## 13. Why more data is required before tightening Production

Early bucket performance can be extremely noisy. High estimated EV can lose over short samples, and low win rate can occur by variance, especially at higher odds.

Before changing Production gates, inspect jointly:

- sample size;
- ROI;
- calibration;
- CLV;
- odds distribution;
- market mix;
- route mix;
- league mix.

Avoid selecting Production buckets because of a small run of wins/losses. The objective is to identify repeatable structure, not recent luck.

## 14. Intended future Production-selection workflow

Do not implement this automatically from small samples.

Once sufficient settled data exists:

1. build bucket/cohort performance tables;
2. identify regions with adequate sample size;
3. inspect calibration and CLV as well as realized ROI;
4. check whether performance persists across time and leagues;
5. define candidate Production filters;
6. keep excluded-but-final-gate candidates in Research so the counterfactual sample continues;
7. only after stable evidence, consider different stake sizing / Kelly behavior.

This preserves the ability to measure whether a stricter Production policy actually removes weaker regions rather than merely hiding them.

## 15. Dashboard expectations

Research dashboard should continue to expose:

- Active and History separately;
- route filter: `PLAYED`, `SKIPPED`, `BLOCKED_EXPOSURE`;
- model-probability bucket filter;
- EV bucket filter;
- odds bucket filter;
- market filter;
- result filter in History;
- prominent score and WIN/LOSS/VOID status;
- CLV;
- flat-stake P/L;
- bookmaker;
- qualification time.

Add market-fair-probability bucket filtering when that bucketization is implemented.

## 16. Data-integrity rules

- Research persistence must never block or alter Production.
- One canonical Research row per fixture.
- Production picks must be present in Research.
- Exposure-only candidates must be present in Research only when exposure is the sole relevant blocker.
- Raw probability, EV, odds, edge, and market probability must remain stored even when bucket labels are added.
- Historical backfills must be deterministic.
- Research settlement must not create fake Production settlement or bankroll events.
- Do not rewrite historical bucket labels retroactively without documenting the change.

## 17. Open analytical TODOs

- [ ] Define market fair probability bucket boundaries.
- [ ] Add market fair probability bucket to Research projection and dashboard filters.
- [ ] Add bucket summary tables with `N`, ROI, calibration, CLV, and positive-CLV rate.
- [ ] Add time-sliced analysis (for example by week) to distinguish persistence from one short run.
- [ ] Add confidence intervals / uncertainty around bucket win rate and ROI.
- [ ] Compare Production routes without treating route as a quality label.
- [ ] Revisit Production selectivity only after enough settled observations accumulate.
- [ ] Consider Kelly / variable staking only after candidate quality is empirically characterized.

## 18. Interpretation rule

The Research dataset exists to answer:

> Which final-gate candidates are actually worth allocating real-money exposure to?

Until the data can answer that with reasonable stability, Production policy should remain conservative and Research should remain broad enough to observe the opportunities that Production does not take.
