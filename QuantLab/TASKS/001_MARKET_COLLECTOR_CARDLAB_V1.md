# Task 001 — QuantLab Market Collector + CardLab v1 Context

## Objective

Build the first working QuantLab data/feature pipeline without changing production prediction, registration, bankroll or existing Research Board behavior.

QuantLab is shadow-only.

## Repository boundary

All new QuantLab runtime code must live under:

```text
src/h2h/quantlab/
```

Lab-specific code must live under one of:

```text
src/h2h/quantlab/goal_lab/
src/h2h/quantlab/corner_lab/
src/h2h/quantlab/card_lab/
```

Architecture/work records must be updated under:

```text
QuantLab/
```

Every implementation step must append a concise record to `QuantLab/WORKLOG.md`.

## Part A — All-market collector

Implement a QuantLab-only pre-match odds collector for:

- Bet365 — API-Football bookmaker ID 8
- 1xBet — API-Football bookmaker ID 11

Requirements:

1. Fetch one fixture-level `/odds?fixture=<id>` response where practical and reuse it for both bookmakers and all returned markets.
2. Do not reuse the production canonical odds adapter that intentionally keeps only bet IDs 5 and 8.
3. Preserve raw provider semantics:
   - provider fixture ID
   - bookmaker ID/name
   - provider bet ID/name
   - raw selection
   - parsed line when deterministic
   - odds
   - provider update timestamp
   - QuantLab capture timestamp
4. Store immutable raw/normalized QuantLab market observations in QuantLab-owned tables.
5. Do not create production `quote_series`, `value_evaluations`, `pick_decisions` or `registered_picks` from this collector.
6. All provider calls must execute under `quantlab_context`.
7. QuantLab daily API hard ceiling remains 1,000 calls.
8. Cache/reuse data aggressively; one fixture request should feed GoalLab, CornerLab and CardLab where possible.

## Part B — Market classification

Create a versioned market classifier that maps raw provider markets into laboratory ownership:

- GoalLab
- CornerLab
- CardLab
- UNCLASSIFIED

Do not discard unknown markets. Preserve them as raw observations with `UNCLASSIFIED` ownership until explicitly supported.

Do not invent settlement semantics from provider names.

## Part C — CardLab v1 feature snapshot

Create a timestamp-safe CardLab feature snapshot for a target fixture/decision time.

CardLab v1 must include the five immediate context variables:

1. `referee_card_rate`
2. `referee_foul_rate`
3. `derby_rivalry_indicator`
4. `table_pressure`
5. `match_importance`

Also persist companion provenance/quality fields needed to interpret them, including referee sample size.

### Referee rules

- Referee identity should come from API-Football fixture data when available.
- Referee rates use only matches completed before the target feature `available_at`.
- No target-match stats may leak into the snapshot.
- Define and version how yellow/red/second-yellow cards are counted.
- Small referee samples must be visible; if shrinkage is implemented, version the formula.

### Derby/rivalry rules

- Use a deterministic, versioned rivalry registry.
- No LLM inference at prediction time.
- Initial value is boolean 0/1.
- Unknown is distinct from confirmed false if source coverage cannot establish the relationship.

### Table pressure rules

Implement a deterministic versioned formula based on pre-kickoff league-table facts.

It must measure distance to relevant competitive thresholds rather than raw rank alone, where applicable:

- title
- promotion/playoff
- continental qualification
- relegation

Persist intermediate components so the score is auditable.

### Match importance rules

Implement a deterministic `MATCH_IMPORTANCE_V1` score using documented inputs such as:

- home table pressure
- away table pressure
- stage of season
- points gap to target
- derby/rivalry indicator
- competition context

Persist intermediate components and version.

## Part D — Dashboard

Extend CardLab dashboard rows/details to expose at minimum:

- referee
- referee cards/match
- referee fouls/match
- referee sample size
- derby/rivalry
- home table pressure
- away table pressure
- match importance
- feature snapshot timestamp/version

Do not fake unavailable values; render missing/unknown explicitly.

## Part E — Tests

Add tests for:

- all-market parser retaining unsupported/raw markets
- Bet365 + 1xBet filtering
- `quantlab_context` budget category
- no production-table writes from QuantLab collector
- timestamp leakage rejection
- referee rates excluding target/future matches
- deterministic rivalry registry
- table-pressure boundary cases
- match-importance determinism/version
- CardLab dashboard displaying feature provenance

## API budget target

Hard limit: **1,000/day**.

Design target: materially below the hard limit on normal days by reusing fixture-level odds payloads and deriving/caching context locally.

## Production safety

This task must not change:

- production Dixon-Coles math
- production pick thresholds
- production bankroll/staking
- production market support
- production registered-pick flow
- existing Research Board semantics

## Definition of done

- QuantLab collector runs independently in `quantbet-quantlab`.
- Bet365/1xBet all-market observations are durably stored.
- Goal/Corner/Card ownership classification is versioned.
- CardLab v1 snapshots contain the five requested context variables with provenance.
- Dashboard surfaces those variables.
- Tests pass.
- `QuantLab/WORKLOG.md` and affected lab docs are updated.
- Railway QuantLab deploy is healthy.
