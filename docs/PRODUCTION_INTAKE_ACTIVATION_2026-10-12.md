# Production intake activation — seven selected cohorts

**Activation status: confirmed by successful Railway Production worker cycle.**

- Frozen pre-activation baseline: [PRODUCTION_INTAKE_BASELINE_2026-10-11.md](PRODUCTION_INTAKE_BASELINE_2026-10-11.md), historical N, W-L-V, ROI for B1–B5 and C4–C5.
- Seven-bucket feature merged into main: `ab36cc8547b21bdb792117e85e3c50a8a6e76171` (#263).
- CornerLab cursor binding hotfix merged into main: `500916726c5fcfef9d613f6ad1f23424af50b09f` (#266). CI successful.
- Railway Production engine deployment: `b223db94-db8a-4e94-81a9-b26b1f80c62e`, status SUCCESS.
- Engine first confirmed successful `production_intake` cycle: **2026-10-11T22:18:09.710326593Z** = **2026-10-12 00:18:09.710 Europe/Belgrade**.
- At cycle start, Production funnel exposure snapshot = `240000` minor RSD; after intake = `450000` minor RSD (2,400 -> 4,500 RSD). Exposure ceiling was not raised.
- Dashboard verification via read-only GitHub Actions run `38179649189` at `2026-10-11T22:14:56–22:14:57Z`: Research 5 blue rows, CornerLab 2 blue rows, HTTP 200; exact IDs matched. Research, QuantLab, Production dashboard services were all online on their seven-bucket-compatible, hotfix-derived commit `bab97d41c8dd6b39e680bf1867a642545a01b6fd`.
- Production's `QUANTBET_PRODUCTION_INTAKE_BUCKETS` explicitly lists the five Research + two CornerLab IDs. QuantLab and Production dashboard were aligned to the identical contract. No GoalLab/CardLab intake selected.
- **Forward performance anchor**: use `2026-10-11T22:18:09.710326593Z`. Evaluate source-cohort signals with `source_decision_at >= anchor` for forward Research/Corner counterfactual ROI, and separately report actual Production picks cloned after the activation cycle with their operator PLAYED/SKIPPED state and realized settlement. Do not count overlapping cohorts as independent bets.

This record is a dated audit anchor, not a dynamic statistic. Do not change the anchor after further results. Historical ROI is not actual post-deploy Production profit.
