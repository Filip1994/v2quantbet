# QuantLab Architecture

## Repository structure

    QuantLab/
    ├── README.md
    ├── ARCHITECTURE.md
    ├── ROADMAP.md
    ├── WORKLOG.md
    ├── CHANGE_PROTOCOL.md
    ├── GoalLab/
    │   └── README.md
    ├── CornerLab/
    │   └── README.md
    └── CardLab/
        ├── README.md
        └── FEATURES_V1.md

    src/h2h/quantlab/
    ├── entrypoint.py
    ├── dashboard.py
    ├── repository.py
    ├── provider.py
    ├── budget.py
    ├── runtime.py
    ├── scope.py
    ├── fixture_discovery.py
    ├── market_collector.py
    ├── market_classifier.py
    ├── goal_lab/
    ├── corner_lab/
    └── card_lab/

## Services

Railway service: quantbet-quantlab.

The service uses the same PostgreSQL instance for shared immutable facts, but QuantLab
writes only QuantLab-owned state. It must not write:

- registered_picks
- pick_decisions
- production quote_series/value_evaluations
- bankroll tables
- active production model state
- production registration policy

## Shared core

The QuantLab core owns:

- API budget accounting
- independent global API-Football date-shard fixture discovery
- all-market Bet365/1xBet ingestion
- versioned zero-request league eligibility
- feature provenance conventions
- append-only shadow decision evidence and shadow-bet ledger
- GoalLab read-only control-model evaluation over active Dixon-Coles artifacts
- settlement conventions
- P&L / ROI / CLV / drawdown reporting
- dashboard routing

## Lab ownership

### GoalLab

Owns goal probabilities and goal-market experiments, including DC+. GOAL_SCOPE_V2 uses a
broad professional-senior universe with explicit youth/amateur, Africa and Far East
exclusions.

### CornerLab

Owns corner probabilities and corner-market experiments. Card/Corner discovery is
market-driven under CARDCORNER_MARKET_DRIVEN_V4: competition name no longer gates
eligibility; persisted market presence and canonical settlement support do.

### CardLab

Owns card/foul probabilities and card-market experiments. Referee and match-context
variables belong here unless a later experiment explicitly demonstrates a justified
cross-lab use. CardLab uses the same market-driven universe and requests referee/context
only after a CARD market has actually been observed for the fixture.

## Data contract

Every feature snapshot carries or can be audited back to:

- fixture_id
- feature name
- feature value
- source
- observed_at / available_at
- feature version
- lab owner
- extraction/calculation version
- quality/coverage where applicable

No feature may use information that became available after the shadow decision timestamp.

Women's football is a global hard exclusion shared with production. QuantLab drops identified women fixtures at date-shard parsing and all lab scopes reject them, including legacy rows already present in the research inventory.

QuantLab owns its fixture universe independently from production Phase-I discovery.
`quantlab_fixtures` stores provider fixture identity; date-shard captures are append-only in
`quantlab_fixture_observations` and `quantlab_fixture_discovery_shards`. Production fixture
and result tables remain read-only historical fallbacks only.

QuantLab-owned Task 001 observation/snapshot tables are append-only:

- quantlab_fixture_observations
- quantlab_fixture_discovery_shards
- quantlab_market_observations
- quantlab_market_captures
- quantlab_fixture_context_observations
- quantlab_match_statistics_observations
- quantlab_statistics_captures
- quantlab_standings_snapshots
- quantlab_card_feature_snapshots
- quantlab_corner_model_versions
- quantlab_corner_feature_snapshots
- quantlab_goal_decisions

## Market collector contract

The QuantLab collector requests one pre-match /odds?fixture=<id> payload and reuses it
for both Bet365 (8), 1xBet (11) and all laboratory classifiers. It does not use the
production canonical adapter that limits supported production markets.

Raw provider bet ID/name, raw selection, deterministic parsed line, odds, provider update
time, QuantLab capture time and classifier version are persisted only when the lab owner
is eligible for that fixture. GOAL rows follow GOAL_SCOPE_V2. CARD, CORNER and
UNCLASSIFIED research follows CARDCORNER_MARKET_DRIVEN_V4 across the global discovered
universe. Successful odds responses also create a quantlab_market_captures watermark even
when zero rows are stored, so empty responses are not re-polled on every cycle or restart.

## GoalLab shadow decision contract

Task 002 adds `GOALLAB_SHADOW_POLICY_V1` as a shadow-only control decision path.

- The model is the already-active, validated production Dixon-Coles artifact for the exact
  API-Football league/season, loaded read-only. QuantLab never activates or mutates it.
- Supported control markets are only O/U 2.5 (provider bet 5) and BTTS (provider bet 8).
- A decision requires a complete two-sided quote from the same bookmaker and capture.
- Fair market probability uses proportional two-way de-vig.
- Default PICK gates are edge >= 3 percentage points, EV >= 3%, odds 1.40-4.00,
  quote age <= 13 hours and at least 15 minutes to kickoff.
- All evaluated outcomes are auditable in `quantlab_goal_decisions`; only PICK outcomes
  may create `quantlab_shadow_bets`.
- Missing model coverage, missing complete markets and policy failures are explicit PASS
  reasons. Probabilities are never fabricated.

Shadow evaluation runs independently of the provider budget, so already-persisted odds can
still be evaluated after the daily API ceiling has stopped collection. Task 002 itself
adds zero provider calls.

## API policy

QuantBet now operates with one shared **75,000 requests/day** football provider envelope.

- `provider_request_usage` remains the durable category telemetry.
- QuantLab requests are still attributed to `quantlab_context`.
- There is no separate 1,000/day QuantLab hard cap.
- There is no reserved 1,500-call production slice in the active QuantLab contract.
- All services stop at the same shared provider envelope.
- Deduplication, cache TTLs, capture watermarks and coverage checks remain mandatory
  because they protect data quality and throughput, not merely cost.

Current broad research defaults:

- global date-shard discovery remains cached;
- upcoming fixture scan limit: 1,000;
- all-market odds refresh: 1 hour;
- historical completed-match statistics backfill: 25 fixtures per 5-minute cycle by
  default, subject to missing-data checks;
- CardLab target context is pulled only when CARD market evidence exists;
- standings/context keep slower TTLs because provider publication cadence is slower.

## Evaluation contract

All labs report the same core metrics:

- log loss / Brier when probabilities are evaluable
- calibration
- CLV
- flat-stake P&L
- ROI/yield
- maximum drawdown
- sample size
- bookmaker split
- league split
- market/line split

QuantLab results never automatically promote a model into production.


## One-time fixture bootstrap

Migration 029 seeds a bounded current snapshot from already-persisted production
`fixtures` / `fixture_observations` only when a fixture has no QuantLab observation.
This bridge makes pre-existing QuantLab market observations evaluable without spending
provider calls during a daily API-ceiling event.

The bootstrap is not an ongoing discovery source and does not replace the independent
global QuantLab date-shard pipeline. Its rows are explicitly marked
`production-fixture-bootstrap`; subsequent provider-discovered QuantLab observations
remain authoritative for normal laboratory operation.

### Context-market decision layer

Migration 030 introduced the shared append-only
`quantlab_context_market_decisions` ledger for CornerLab and CardLab.

CardLab still uses `CROSS_BOOK_FAIR_REFERENCE_CARD_CONTEXT_V1` with its referee/context
gate.

CornerLab V1's `CROSS_BOOK_FAIR_REFERENCE_V1` is retained only as a historical baseline.

### CornerLab V2 structural model

Task 004 replaces the active CornerLab probability source with
`CORNER_PRESSURE_POISSON_V1`.

- Historical fixture statistics now retain corner, possession, shot, territorial and
  passing variables.
- `quantlab_statistics_captures` watermarks AVAILABLE and UNAVAILABLE provider coverage.
- A ridge-regularized Poisson GLM is trained once per decision cycle using only earlier
  historical matches.
- The model uses recent and venue-specific corner/pressure features.
- Bookmaker odds are excluded from training.
- `quantlab_corner_model_versions` stores coefficients, means/scales and training
  provenance.
- `quantlab_corner_feature_snapshots` stores the exact target feature vector and expected
  total corners.
- A complete one-bookmaker Over/Under corner pair is sufficient for value evaluation;
  cross-book agreement is no longer a CornerLab PICK prerequisite.

The evaluator remains shadow-only and has no production pick, bankroll or active-model
write path.
