# QuantBet

QuantBet is a production pre-match football betting research and execution system with three deliberately separated sectors:

1. **Production** — live opportunity discovery, model execution, value/eligibility/risk decisions, pick registration, monitoring, settlement and bankroll accounting.
2. **Research** — read-only analysis of the comparable final-gate candidate universe, including Production picks and exposure-blocked candidates.
3. **QuantLab** — isolated multi-market laboratories for GoalLab, CornerLab and CardLab. QuantLab has no direct Production write authority.

> **Documentation rule:** use [PROJECT_STATUS.md](./PROJECT_STATUS.md) for the current system snapshot and [docs/CURRENT_PRIORITIES.md](./docs/CURRENT_PRIORITIES.md) for the active priority/governance queue. Dated audits, task files and work logs are historical evidence, not current-state authority.

## Production architecture

- GitHub is the source-code and CI system.
- Railway runs the production services.
- Railway PostgreSQL is the canonical durable store.
- Production is strictly pre-match.
- Quote, decision, registered-pick, settlement and bankroll evidence is durable and auditable.
- Production does not fall back to SQLite.
- Model/policy identities and decision-affecting versions are persisted.
- Same-bookmaker closing/CLV is preserved where a valid closing observation exists.

The production pipeline is already end-to-end:

```text
fixture discovery
→ model coverage / prediction
→ odds ingestion
→ de-vig + value evaluation
→ eligibility / freshness / risk
→ final quote verification
→ durable pick registration
→ monitoring / closing
→ result acquisition
→ settlement / bankroll / realized CLV
```

## Research

Research is a read-only superset of the comparable Production decision universe. Its purpose is to understand where model/market/value signals are strong or weak without contaminating the Production sample.

Current Research analytics include bucket/cohort breakdowns, drilldowns to constituent picks, model/policy regimes, time slices, ROI, calibration, CLV and Wilson win-rate intervals.

Research never changes Production automatically.

## QuantLab

QuantLab is isolated from Production writes and currently contains:

- **GoalLab** — DC+ Pro Structural goals/BTTS research with compact V2 structural features, chronological validation and exact-model manual authority control.
- **CornerLab** — structural pressure-Poisson corner model, currently constrained mainly by historical/team-stat coverage.
- **CardLab** — referee-Poisson card research, currently constrained mainly by referee-history/data coverage.

GoalLab and CornerLab analytics expose a first-class **Watchlist · ROI discovery** area with cross-feature bucket views and drilldowns to the exact settled picks behind each cohort.

## Governance

- No analytics table can automatically mutate Production.
- A Research/QuantLab bucket may enter Production selection only through an explicit owner decision.
- Forward/OOS confirmation is useful evidence but is **not a mandatory approval gate** for an owner-approved bucket rule.
- Permanent bucket bans are intentionally slow: default review horizon is **3–6 months**.
- Leakage, settlement bugs, bad identity mapping, corrupted data or other technical-integrity failures may trigger immediate suspension without waiting 3–6 months.

## Current engineering caveat

At the 2026-09-30 documentation sync point, the audited `main` SHA `0733299` had failing GitHub CI at the Ruff step. This is a release-discipline issue, not evidence that the deployed Railway services are down. The exact active actions are tracked in [docs/CURRENT_PRIORITIES.md](./docs/CURRENT_PRIORITIES.md).

## Documentation

Start here:

- [PROJECT_STATUS.md](./PROJECT_STATUS.md) — current system snapshot.
- [docs/CURRENT_PRIORITIES.md](./docs/CURRENT_PRIORITIES.md) — current priorities and owner governance.
- [docs/README.md](./docs/README.md) — complete Markdown inventory and document-status map.
- [md/research-analysis-framework.md](./md/research-analysis-framework.md) — current Research dataset/analytics contract.
- [QuantLab/README.md](./QuantLab/README.md) — QuantLab overview.
- [QuantLab/GoalLab/README.md](./QuantLab/GoalLab/README.md) — GoalLab.
- [QuantLab/CornerLab/README.md](./QuantLab/CornerLab/README.md) — CornerLab.
- [QuantLab/CardLab/README.md](./QuantLab/CardLab/README.md) — CardLab.
