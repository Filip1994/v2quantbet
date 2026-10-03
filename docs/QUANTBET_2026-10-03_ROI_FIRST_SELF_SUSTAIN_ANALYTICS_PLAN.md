# QuantBet ROI-First Self-Sustain & Research Analytics Plan

**Date:** 2026-10-03  
**Status:** Active implementation plan  
**Scope:** Football Research Analytics / prematch betting model

## 1. Operating objective

QuantBet's immediate operating objective is to become **monthly self-sustaining** while working with a pilot bankroll of approximately **30,000 RSD**.

This is an operating target, not a guarantee of profitability. The system should first prove that its prematch selection process can produce persistent positive realized return before capital allocation or filtering becomes more aggressive.

The current north-star metric is therefore:

> **Realized flat-stake ROI on settled prematch picks.**

Monthly P&L, drawdown and bankroll survival remain operational constraints around that objective.

## 2. Why ROI is the current primary metric

The current data provider is statistics-oriented rather than an odds-specialized feed. Odds observations can be several hours apart, so the currently stored "closing" observation is not guaranteed to be a true market close.

For the present phase:

- ROI is the primary profitability metric;
- sample size and uncertainty determine how much confidence to place in ROI;
- temporal persistence is required before pruning;
- calibration remains a model-quality diagnostic;
- CLV is retained, but it is **not currently a production pruning gate**.

## 3. CLV stays in the architecture

CLV must **not** be removed.

The long-term plan is to cross QuantBet with an **odds-specialized API** that can provide denser and more reliable bookmaker price histories / closing references.

When that data is available:

1. preserve entry bookmaker, market and exact selection identity;
2. obtain a reliable closing reference from the specialized odds source;
3. validate source/bookmaker alignment;
4. recompute CLV with explicit provenance;
5. cross CLV with ROI, market, selection, league, edge, odds and time-to-kickoff;
6. determine empirically whether CLV adds predictive or governance value for QuantBet.

Until then, existing CLV remains visible as a research axis and should not independently KEEP/BAN a bucket.

## 4. Analytics design: low-dimensional first

The main Analytics page should prioritize buckets that can accumulate enough observations to become decision-grade.

### Primary decision buckets

- Market × selection
- Entry odds
- Edge
- Time-to-kickoff
- League
- Market × selection × entry odds
- Market × selection × edge
- League × market × selection
- Weekly / temporal stability

### Secondary research axes

- Model probability
- Market fair probability
- Expected value
- Calibration
- CLV

### Audit-only detail

The following remain available for provenance and debugging but should not dominate the main decision surface:

- model version;
- policy configuration;
- model × policy;
- decision contract;
- specialized research diagnostics.

The previous high-dimensional **Production filter cube** is removed from the main analytics contract because it fragments the sample into mostly non-actionable micro-buckets.

## 5. ROI evidence shown per bucket

Decision tables should expose, at minimum:

- settled N;
- W-L-V;
- lifetime ROI;
- approximate 95% ROI interval;
- ROI over the last 100 graded picks, when N >= 100;
- ROI over the last 250 graded picks, when N >= 250;
- ROI over the last 500 graded picks, when N >= 500;
- average entry odds;
- average model edge;
- evidence maturity;
- direct drilldown to constituent picks.

A trailing ROI is deliberately hidden until the bucket contains at least that many graded observations. This prevents "last 250" from silently meaning "all 37 picks".

## 6. Evidence maturity / pruning thresholds

These bands are descriptive and **must not automatically place or block bets**.

| Graded N | Evidence stage | Allowed interpretation |
|---:|---|---|
| <100 | COLLECT | No pruning conclusion |
| 100–249 | WATCH | Flag patterns only |
| 250–499 | SOFT_REVIEW | Candidate for deeper review |
| 500–999 | DECISION_GRADE | Sufficient for formal pruning review |
| 1000+ | MATURE | Stronger long-run evidence |

A negative raw ROI alone is not enough for a ban.

Pruning should consider:

- N;
- ROI magnitude;
- ROI uncertainty / confidence interval;
- lifetime vs trailing 100/250/500 consistency;
- model / policy regime changes;
- out-of-sample confirmation;
- operational relevance of the bucket.

## 7. Proposed pruning discipline

### KEEP candidate

A bucket can become a KEEP candidate when it has:

- sufficient sample size;
- positive lifetime ROI;
- positive or stable recent-window ROI;
- no clear evidence that results come from one temporary model regime only.

### WATCH / SOFT_REVIEW

Use when:

- sample is still limited;
- ROI is unstable across windows;
- confidence interval is wide;
- model retrains materially changed behavior.

### BAN candidate

Do not create an automatic hard ban from a single red ROI number.

A formal BAN candidate should normally require:

- at least decision-grade sample size;
- persistently negative ROI;
- uncertainty that meaningfully favors negative expectation;
- confirmation across recent windows or a separate validation period.

Production enforcement should remain a separate, explicit step from Research Analytics.

## 8. Multiple-testing / overfitting control

QuantBet will inspect many possible buckets. Some will appear excellent or terrible by chance.

Therefore:

1. use the historical sample for discovery;
2. freeze the proposed bucket rule;
3. validate it on subsequent unseen picks;
4. only then consider changing stake or production eligibility.

The goal is not to find the prettiest historical ROI. The goal is to identify edges that survive new data.

## 9. 2026-10-03 implementation scope

The Research Analytics redesign initiated on this date includes:

- ROI-first decision surface;
- edge buckets;
- time-to-kickoff buckets;
- Market × selection × odds;
- Market × selection × edge;
- League × market × selection;
- rolling ROI 100 / 250 / 500;
- approximate ROI uncertainty;
- modernized sortable tables;
- audit detail moved away from the main decision surface;
- CLV retained with an explicit "research / future odds API" role;
- removal of the high-dimensional Production filter cube.

## 10. Near-term success criteria

Before QuantBet starts aggressive pruning:

- gather materially larger samples per candidate bucket;
- keep the Research universe broad enough to learn;
- measure monthly realized P&L and ROI;
- identify stable negative and positive cohorts;
- validate candidates on fresh data;
- only then introduce production KEEP / SOFT BAN / BAN controls.

The immediate objective is **learning without destroying sample diversity**, while giving the 30,000 RSD pilot bankroll the best chance to demonstrate sustainable monthly economics.
