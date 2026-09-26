# Task 001 — QuantLab Market Collector + CardLab v1 Context

> **Superseded scope note (2026-09-26):** the historical Top-10 budget gate described below was replaced by `CARDCORNER_MARKET_DRIVEN_V3` after the football provider budget increased to 75,000 requests/day. The remainder of this file records the implementation contract as it existed at the time.

Status: implemented on main; verification record is maintained in QuantLab/WORKLOG.md.

## Objective

Build the first working QuantLab data/feature pipeline without changing production
prediction, registration, bankroll or existing Research Board behavior.

QuantLab is shadow-only.

## Repository boundary

All new QuantLab runtime code lives under src/h2h/quantlab/. Lab-specific code remains
physically separated under goal_lab/, corner_lab/ and card_lab/.

Architecture/work records are maintained under QuantLab/. Every implementation change
must be recorded in QuantLab/WORKLOG.md.

## Part A — All-market collector

Implemented QuantLab-only pre-match odds collection for:

- Bet365 — API-Football bookmaker ID 8
- 1xBet — bookmaker ID 11

Contract:

1. One fixture-level /odds?fixture=<id> response is reused across both bookmakers and all
   laboratory ownership classification.
2. The production canonical odds adapter is not used.
3. Provider fixture ID, bookmaker ID/name, provider bet ID/name, raw selection,
   deterministic parsed line, odds, provider update timestamp and capture timestamp are
   preserved for lab-eligible rows.
4. GOAL rows may be persisted across GOAL_SCOPE_V1. CARD, CORNER and UNCLASSIFIED rows
   are persisted only for CARDCORNER_TOP10_LEAGUES_V2 fixtures.
5. Every successful odds response writes an append-only market-capture watermark even
   when zero rows are stored, preventing empty-result re-poll loops across cycles/restarts.
6. Observations and capture watermarks are stored in QuantLab-owned tables.
7. The collector has no write path to quote_series, value_evaluations, pick_decisions,
   registered_picks or bankroll.
8. Provider calls execute as quantlab_context.
9. QuantLab cannot exceed 1,000 calls/day.
10. Shared-provider reserve stops QuantLab before production capacity is endangered.

## Part B — Market classification

MARKET_CLASSIFIER_V1 maps raw provider names to GOAL, CORNER, CARD or UNCLASSIFIED.
Unknown markets are preserved, not discarded. Classification is ownership only and does
not invent settlement semantics.

## Part C — CardLab v1 feature snapshot

Implemented CARDLAB_FEATURES_V1 with:

1. referee_card_rate
2. referee_foul_rate
3. derby_rivalry_indicator
4. table_pressure
5. match_importance

Exact definitions, provenance, quality fields and formulas are frozen in
QuantLab/CardLab/FEATURES_V1.md.

All inputs must have available_at not later than decision_at, and decision_at must be
before kickoff. Referee history excludes target/future matches and historical facts
backfilled after an old decision do not become retroactively eligible.

## Part D — Fixture universe and League/API scope refinement

Added after implementation review to reduce waste without inheriting production's narrower
fixture universe.

QuantLab owns global date-shard discovery through `/fixtures?date=<UTC date>` and persists
that universe in `quantlab_fixtures`, `quantlab_fixture_observations` and
`quantlab_fixture_discovery_shards`. Production fixture/result tables are read-only
historical fallback and do not define QuantLab eligibility.

CARDCORNER_TOP10_LEAGUES_V2 gates CardLab/CornerLab fixture-specific spend to exactly
ten domestic top flights: Premier League, La Liga, Serie A, Bundesliga, Ligue 1,
Eredivisie, Primeira Liga, Belgian Pro League, Süper Lig and Major League Soccer (MLS).
Lower divisions, cups and UEFA club competitions are rejected locally for those labs.

GOAL_SCOPE_V1 remains broad but excludes:

- youth U5-U23 and equivalent Under labels;
- academy/reserve/amateur/junior/olympic competitions;
- Africa;
- the V1 Far East country registry.

The scope gate runs after zero/low-cost date-shard discovery and before fixture-specific
odds/context/statistics calls.

## Part E — Dashboard

CardLab exposes referee, cards/match, fouls/match, both sample sizes, rivalry state,
home/away table pressure, match importance, feature timestamp/version and provenance.
Unavailable/unknown values are rendered explicitly rather than fabricated.

## Part F — Tests

Task tests cover:

- independent global fixture discovery before lab scope;
- zero fixture-specific calls for locally excluded fixtures;
- QuantLab-only fixture persistence with no production fixture writes;
- unsupported/raw market retention;
- Bet365 + 1xBet filtering;
- one-response fixture reuse;
- quantlab_context categorization;
- hard 1,000-call ceiling and production reserve;
- no production-table write path from the collector;
- league-scope API gating;
- timestamp leakage rejection;
- referee history exclusion;
- deterministic rivalry registry;
- table-pressure boundaries;
- match-importance determinism/version;
- CardLab dashboard provenance.

## API budget target

Hard limit: 1,000/day.

Design target: materially below the hard limit through global date-shard discovery cached
for six hours, local zero-request scope filtering, fixture-response reuse, persistent
capture watermarks, a 12-hour default odds refresh, a 6-hour default standings refresh
and no automatic historical statistics backfill by default.

## Production safety

This task does not change:

- production Dixon-Coles math
- production pick thresholds
- production bankroll/staking
- production market support
- production registered-pick flow
- existing Research Board semantics

## Definition of done

- QuantLab collector runs independently in quantbet-quantlab.
- QuantLab fixture discovery is independent from production Phase-I scope.
- Bet365/1xBet market observations are durably stored only for fixture-eligible lab owners.
- Successful empty odds responses are durably watermarked and do not trigger 5-minute
  re-poll loops.
- Goal/Corner/Card ownership classification is versioned.
- CardLab v1 snapshots contain the five requested context variables with provenance.
- Dashboard surfaces those variables.
- Tests pass.
- QuantLab/WORKLOG.md and affected lab docs are updated.
- Railway QuantLab deploy is healthy.
