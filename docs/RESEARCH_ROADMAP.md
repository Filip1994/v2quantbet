# QuantBet Research Roadmap

**Status:** Future side project — not part of the current production implementation.

**Recorded:** 2026-09-12 19:16 (Europe/Belgrade)

## Purpose

Build a separate research capability that can use long-term historical football and odds data to discover patterns, engineer features, train models, and eventually produce independently evaluated research signals.

## Scope deferred for later

- Long-term collection of API-Football data.
- Continuous pre-match odds collection, including a configurable scan window such as 72 hours before kickoff.
- Immutable storage of raw API responses and odds observations.
- Historical odds movement analysis for `OU_25` and `BTTS` first.
- Feature engineering using fixtures, teams, leagues, results, statistics, events, injuries, lineups, and other available provider data.
- Research datasets, backtesting, model training, experiment tracking, and model versioning.
- A separate research signal layer that can propose candidate picks without directly changing production decisions.

## Data-infrastructure direction

Railway should primarily host operational production services and hot data. It should not be treated as the permanent archive for every raw API response.

The future architecture should separate:

1. **Production storage:** active fixtures, current market state, operational records, and data needed for live QuantBet decisions.
2. **Archive storage:** immutable raw API responses and historical odds data in external object storage, preferably an S3-compatible service.
3. **Research storage/compute:** analytical datasets such as Parquet, queried with an analytical engine such as DuckDB or a dedicated warehouse when scale requires it.

No historical odds data should be deleted merely to control Railway storage growth. Retention and archival policies must preserve the raw source data.

## Research isolation rules

- Research must not directly modify production picks, bankroll, risk controls, or settlement records.
- Production and research may share canonical schemas, fixture identifiers, market definitions, and validation contracts.
- Research signals must be versioned, backtested, and independently evaluated before any production integration.
- A Git branch is not sufficient runtime isolation; research should eventually run as a separate process/service with separate configuration.

## Deferred implementation sequence

1. Build reliable production ingestion and canonical odds normalization.
2. Measure actual API response sizes, request volume, and storage growth.
3. Add immutable raw-response archiving.
4. Add configurable 72-hour pre-match collection and scheduling.
5. Build research ETL and historical datasets.
6. Implement feature engineering and reproducible backtests.
7. Train and evaluate research models.
8. Expose research signals as a separate, controlled interface.
9. Consider production integration only after objective validation.

## Current decision

Research is intentionally deferred. The immediate priority is to validate the API-Football response format and build the smallest reliable production ingestion path before implementing research infrastructure.
