# CardLab v1 Feature Contract

Status: implemented in Task 001. Definitions below are frozen for CARDLAB_FEATURES_V1; future changes require a new version.

## Scope

CardLab v1 spends fixture-specific API budget only inside CARDCORNER_TOP10_LEAGUES_V2.
The allowlist is implemented in src/h2h/quantlab/scope.py and is shared with CornerLab.

The eligible domestic top flights are Premier League, La Liga, Serie A, Bundesliga,
Ligue 1, Eredivisie, Primeira Liga, Belgian Pro League, Süper Lig and Major League
Soccer (MLS).

Lower divisions, cups, UEFA club competitions, youth, academy, reserve and amateur
competitions are excluded before fixture-specific CardLab calls. Outside the allowlist,
CardLab spends zero fixture-specific API requests.

## Immediate match-context features

### 1. referee_card_rate

Version: CARD_COUNT_RULE_V1.

Historical cards per match for the assigned referee, using only matches whose kickoff and QuantLab observation availability are both before the target decision_at.

Counting rule:

- one count per provider-reported yellow card;
- one count per provider-reported red card;
- one additional count per second-yellow card only when the provider exposes that field separately;
- an unavailable card component is never fabricated as an observed value.

The rate sample includes only historical matches with sufficient card fields for the frozen rule. No shrinkage is used in V1.

Required companion fields: referee_sample_size, source, available_at, quality and calculation version. Quality is NO_HISTORY, SMALL_SAMPLE for fewer than five matches, or OBSERVED.

### 2. referee_foul_rate

Version: CARDLAB_FEATURES_V1.

Historical total fouls per match for the assigned referee, using only eligible completed matches available by decision_at.

Required companion fields: referee_foul_sample_size, source, available_at, quality and feature version.

### 3. derby_rivalry_indicator

Registry version: RIVALRY_REGISTRY_V1.

The value comes only from the deterministic registry in src/h2h/quantlab/card_lab/rivalry.py. No LLM, headline, live web inference or team-name similarity is allowed at prediction time.

Representation:

- 1 = pair is explicitly registered as a rivalry;
- 0 = pair is explicitly registered as confirmed non-rivalry;
- NULL/unknown = registry coverage cannot establish either state.

V1 begins with a conservative positive registry; unlisted pairs are unknown, not automatically false. Registry provenance and release availability are persisted.

### 4. table_pressure

Version: TABLE_PRESSURE_V1.

Input is an API-Football standings snapshot whose available_at is not later than decision_at.

Formula for each relevant competitive threshold:

    threshold_pressure = max(0, 1 - min(abs(team_points - threshold_points), 12) / 12)

Top-flight thresholds are title rank 1, continental rank 4 bounded by table size, and the third-from-bottom relegation threshold.

Recognized second-tier thresholds are automatic promotion rank 2, playoff rank 6, and the third-from-bottom relegation threshold.

The team score is the maximum pressure across applicable thresholds. Persisted components include team rank, team points, table size, threshold rank, threshold points, points gap and per-threshold pressure.

CardLab stores home_table_pressure, away_table_pressure, and table_pressure as the maximum of the available home/away values. Missing standings remain missing.

### 5. match_importance

Version: MATCH_IMPORTANCE_V1.

The deterministic V1 weights are:

- 0.45 — maximum of home/away table pressure;
- 0.20 — mean home/away table pressure;
- 0.15 — stage of season;
- 0.10 — derby/rivalry indicator;
- 0.10 — competition context.

Stage of season is played_matches / (2 * (table_size - 1)), bounded to [0, 1].

Competition context is 1.0 for cup / Champions League / Europa League / Conference League contexts and 0.35 for an ordinary league context.

When an input is unavailable, V1 does not invent it. The score is normalized across the available weighted inputs and provenance records coverage_weight; incomplete snapshots are marked PARTIAL.

## Provenance and leakage contract

Every persisted feature component records value, source, available_at, version, quality, auditable intermediate components and lab owner CARD.

Hard rules:

1. decision_at must be before target kickoff.
2. No source with available_at later than decision_at may enter the snapshot.
3. Target-match statistics are never used for that target snapshot.
4. Referee history queries include only earlier matches and earlier/equal availability.
5. Standings snapshots are selected only from captures available by the decision time.
6. A historical fact backfilled after an old decision is not retroactively considered available at that old decision.

## Provider inputs and API cost

CardLab can use:

- /fixtures?id=<fixture>&timezone=UTC for target/historical referee identity;
- /fixtures/statistics?fixture=<fixture> for completed-match fouls/cards;
- /standings?league=<league>&season=<season> for table state.

Rules reducing spend:

- shared immutable fixture facts are read from PostgreSQL first;
- scope eligibility is resolved locally before fixture-specific calls;
- historical statistics are not requested when the provider fixture record has no referee;
- standings are cached per league/season;
- one fixture-level odds response is reused across GoalLab, CornerLab and CardLab;
- all provider calls are categorized quantlab_context.

QuantLab remains shadow-only.
