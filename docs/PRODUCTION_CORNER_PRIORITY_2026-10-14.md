# Production priority: CornerLab C5, C4, then Research (2026-10-14)

## Operator decision

When eligible candidates compete for free Production exposure, consume these buckets in this order:

1. **CornerLab C5** — `CORNER_OVER_MODEL_50_55_MARKET_45_50_ODDS_1_81_2_00`
2. **CornerLab C4** — `CORNER_OVER_GAP_1_2_ODDS_1_61_1_80`
3. All remaining enabled Research/GoalLab buckets, ranked by existing evidence-weighted lifetime ROI (`ROI * min(graded_N / 100, 1)`). EV and edge break ties within a bucket.

Only the existing approved seven cohorts are eligible in current Production. The change is **ordering only**: do not change approval rules, sample thresholds, stake, risk policy, competition bans, intake list, or the 4,500 RSD total open-exposure cap. Exactly one production pick per fixture continues to apply.

## Execution semantics and limitations

- The scheduler evaluates C5 and C4 before Research **within each future intake cycle**.
- Already registered Production picks retain their operator state and exposure. The scheduler does not preempt, skip, void, or replace an existing pick.
- When open exposure already equals the cap, *zero* new picks of any kind can be admitted, even if C5 is available. Priority does not reserve capacity for later-arriving corners. Any reservation would require a separate explicit decision and policy.
- Dynamic ROI remains the tie-break ordering for non-Corner buckets. C5/C4 take precedence even if their empirical ROI changes; monitor forward ROI to reassess this operator override.
- The new policy is recorded under `PRODUCTION_FUNNEL_INTAKE_V4` with a policy marker in the version fingerprint; it is not confused with prior V3-ranked picks.

## Post-deployment read-only checks

1. Confirm Railway engine deployment completed and the `production_intake` worker is running.
2. On the first cycle with free exposure and simultaneously eligible C5, C4 and Research candidates, verify that **new** `production_funnel_picks` rows carry `production_primary_bucket_id=C5` first, then C4, then Research, and a `PRODUCTION_FUNNEL_INTAKE_V4` contract.
3. Verify `cloned_picks`, `exposure_blocked`, `open_exposure_minor`, no duplicate fixture IDs, and preservation of existing PLAYED/SKIPPED states and settlements.
4. Separately measure **forward** C5/C4 graded N, flat-stake ROI, P/L and admitted-vs-blocked count. The 2026-10-11 historical snapshots (C4: N29, ROI +31.90%; C5: N26, ROI +29.81%) are **not** forward validation or live profit.

No database migration, API contract change, exposure increase, or additional Railway service is required.
