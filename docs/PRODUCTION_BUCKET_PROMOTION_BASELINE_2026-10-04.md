# Production Bucket Promotion Baseline — 2026-10-04

Status: **immutable historical baseline**

Purpose: preserve the metrics that are provably known at the moment the six source buckets were promoted into the Production funnel, so future evaluation can be strictly **apple-to-apple** and does not move the starting point retroactively.

## Promotion anchor

The source-cloned Production funnel and its six-bucket intake contract were introduced in:

- commit: `10b7152e35002e5e786355809bd0042c90ef0fd6`
- committed at: **2026-10-04T00:09:15Z**
- Europe/Belgrade: **2026-10-04 02:09:15 +02:00**
- commit title: `Turn Production into a source-cloned intake funnel`

That commit explicitly configured all six bucket IDs in `QUANTBET_PRODUCTION_INTAKE_BUCKETS`.

## Promotion metric snapshot

The first explicit, durable ROI snapshot for the same six approved buckets was committed 29 minutes later in:

- commit: `d1b23b8a6c50685e71468dd79494613162138fd8`
- committed at: **2026-10-04T00:38:20Z**
- Europe/Belgrade: **2026-10-04 02:38:20 +02:00**
- commit title: `Prioritize Production by bucket ROI and highlight intake cohorts`

These ROI values were written into the shared Production bucket contract as `reference_roi_pct`. They are therefore the authoritative recoverable selection-time ROI snapshot.

| Bucket ID | Source | Definition at promotion | Baseline ROI |
|---|---|---|---:|
| `RESEARCH_OU_UNDER_EDGE_10_15` | RESEARCH | OU 2.5 UNDER, edge 10–15% | **+32.19%** |
| `RESEARCH_OU_UNDER_EDGE_20_30` | RESEARCH | OU 2.5 UNDER, edge 20–30% | **+22.55%** |
| `RESEARCH_BTTS_NO_ODDS_2_01_2_50` | RESEARCH | BTTS NO, odds 2.01–2.50 | **+20.59%** |
| `GOALLAB_OU_OVER_XG_2_5_3_0` | GOALLAB | OU 2.5 OVER, expected total goals 2.5–3.0 | **+17.96%** |
| `GOALLAB_OU_OVER_ODDS_2_01_2_50` | GOALLAB | OU 2.5 OVER, odds 2.01–2.50 | **+17.00%** |
| `RESEARCH_LOW_SCORING_NON_EXTREME` | RESEARCH | low-scoring cohort, EV < 30% and edge < 20% | **+10.29%** |

## Metrics that are not historically proven

The Git history preserves the selection-time ROI values, but it does **not** preserve a complete immutable row for:

- graded N;
- W-L-V;
- flat P/L;
- average odds;
- CLV.

Those values must not be backfilled from today's aggregate state and labelled as selection-time facts.

A read-only database reconstruction should only fill them if the historical source ledgers can be filtered deterministically to evidence available at the promotion cutoff. Until then they remain **UNKNOWN**, not estimated.

## Apple-to-apple evaluation rule

For future evaluation, do not move or recompute this baseline.

For each bucket:

1. keep the definition/version fixed;
2. use the Promotion anchor as the start of forward observation;
3. calculate forward metrics only from source decisions/picks that occur after promotion;
4. compare the immutable baseline ROI above with forward N + ROI;
5. if the bucket definition changes materially, create a new baseline/version rather than rewriting this record.

The primary comparison is:

```text
selection-time baseline
vs
post-promotion forward performance
```

This file is historical evidence. It must not be rewritten merely because later performance changes.
