# CardLab v1 Feature Contract

Status: foundation contract. Exact coefficients are learned/tested later; feature definitions must remain deterministic and timestamp-safe.

## Team profile

CardLab v1 is expected to include historical team-level card/foul context such as card rates, foul rates, recent form and home/away splits where source coverage is sufficient.

## Immediate match-context features

### 1. `referee_card_rate`

Historical cards per match for the assigned referee, calculated only from matches completed before the target fixture's decision timestamp.

Required companion field: `referee_sample_size`.

A later implementation may use shrinkage toward league mean for small samples, but the method must be versioned.

### 2. `referee_foul_rate`

Historical fouls called per match for the assigned referee, again using only prior eligible matches.

Required companion field: `referee_foul_sample_size`.

### 3. `derby_rivalry_indicator`

Deterministic indicator derived from a versioned rivalry registry. It must not be inferred ad hoc from an LLM, news headline or team-name similarity.

Initial representation: boolean `0/1`. A later `rivalry_strength` feature may be separately introduced.

### 4. `table_pressure`

A deterministic score derived from league-table state available before kickoff.

It should reflect distance to relevant competitive thresholds rather than raw rank alone, including where applicable:

- title race
- promotion/playoff race
- continental qualification
- relegation survival

The exact formula is to be specified and versioned before model training.

### 5. `match_importance`

A deterministic, versioned composite score representing competitive importance. Candidate inputs:

- home table pressure
- away table pressure
- stage of season
- points gap to relevant target
- derby/rivalry indicator
- competition context

The formula must be frozen as a version before historical evaluation.

## Provenance

Every feature snapshot must record `available_at` and source/version so that no post-kickoff or post-decision information leaks into training/backtests.

## API-cost principle

Referee identity should be captured from fixture data whenever available. Referee rates, rivalry registry, table pressure and match importance should be cached/derived locally after raw facts are acquired, rather than repeatedly fetched per market.
