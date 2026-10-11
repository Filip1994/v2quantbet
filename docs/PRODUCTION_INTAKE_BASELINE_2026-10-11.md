# Production intake selection baseline — 2026-10-11

**Status: IMMUTABLE, pre-activation evidence snapshot.**
Captured by read-only public Research analytics JSON and QuantLab Corner analytics HTML via GitHub Actions, at approximately **2026-10-11 22:02–22:05 UTC** (2026-10-12 00:02–00:05 Europe/Belgrade).
The decision to promote these cohorts was made after the snapshot. This historical state MUST NOT be recomputed or overwritten when cumulative source metrics change.

The original [2026-10-04 baseline](PRODUCTION_BUCKET_PROMOTION_BASELINE_2026-10-04.md) remains untouched.

| Selection | Production bucket ID | Source | N graded (W+L) | W-L-V | ROI (lifetime at snapshot) |
|---|---|---|---:|---|---:|
| B1 | `RESEARCH_BTTS_NO_ODDS_2_01_2_50` | Research | 71 | 39-32-1 | +22.25% |
| B2 | `RESEARCH_OU_UNDER_ODDS_2_01_2_50` | Research | 115 | 60-55-0 | +15.88% |
| B3 | `RESEARCH_OU_OVER_ODDS_1_81_2_00` | Research | 48 | 30-18-0 | +19.17% |
| B4 | `RESEARCH_OU_UNDER_EDGE_10_15` | Research | 62 | 35-27-0 | +24.71% |
| B5 | `RESEARCH_OU_UNDER_EDGE_20_30` | Research | 46 | 24-22-0 | +14.04% |
| C4 | `CORNER_OVER_GAP_1_2_ODDS_1_61_1_80` | CornerLab | 29 | 22-7-0 | +31.90% |
| C5 | `CORNER_OVER_MODEL_50_55_MARKET_45_50_ODDS_1_81_2_00` | CornerLab | 26 | 17-9-0 | +29.81% |

**Source caveats**
- Graded N excludes VOID. B1 shows 72 terminal results but 71 graded bets.
- C4 and C5 are **distinct analytics cross-sections** selected from the entire eligible CornerLab history; odds/line/probability predicates are encoded in the contract. Historical CornerLab multi-pick fixtures are normalized to the one settled quote closest to odds 2.00 (tie by ID).
- Baseline is *in-sample lifetime performance*, not prospective profit or validated forward ROI. Do not treat this as money earned by the new Production intake.
- B2, B4 and B5 can overlap; each source pick is cloned at most once. With capacity constrained, the funnel prioritizes live evidence-weighted ROI. Across all universes, Production preserves the unique-fixture constraint.

**Forward measurement protocol (mandatory)**
1. Record exact live deployment timestamp/commit as the **activation anchor**, separately from this pre-activation snapshot; never retroactively include earlier picks as forward observations.
2. Compare each bucket's *new* independently settled bets with source_decision_at >= activation anchor against this immutable selection-time snapshot. Track forward N, W-L-V, flat-stake ROI, P/L, and 100-bet rolling ROI. Distinguish source-bucket counterfactual performance from actual Production PLAYED bets and avoid counting shared picks twice.
3. Record model/policy versions, bookmaker, actual price and classification evidence. VOID must not contribute to graded N or ROI denominator.
4. Report changes with current lifetime N/ROI *and* post-activation forward N/ROI. Today's historical ROI cannot be claimed as forward improvement.

Source evidence: `/research/analytics.json` and `/quantlab?view=analytics&lab=corner`, read-only Actions audit: https://github.com/Filip1994/v2quantbet/actions/runs/38178847719 (Research / Corner), with intersection cross-checks in subsequent runs.
