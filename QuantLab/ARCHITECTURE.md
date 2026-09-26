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

Owns goal probabilities and goal-market experiments, including DC+. GOAL_SCOPE_V1 uses a
broad professional-senior universe with explicit youth/amateur, Africa and Far East
exclusions.

### CornerLab

Owns corner probabilities and corner-market experiments. Fixture-specific spend is
restricted by CARDCORNER_TOP10_LEAGUES_V2.

### CardLab

Owns card/foul probabilities and card-market experiments. Referee and match-context
variables belong here unless a later experiment explicitly demonstrates a justified
cross-lab use. Fixture-specific spend is restricted by CARDCORNER_TOP10_LEAGUES_V2.

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
- quantlab_standings_snapshots
- quantlab_card_feature_snapshots
- quantlab_goal_decisions
- quantlab_goal_decisions

## Market collector contract

The QuantLab collector requests one pre-match /odds?fixture=<id> payload and reuses it
for both Bet365 (8), 1xBet (11) and all laboratory classifiers. It does not use the
production canonical adapter that limits supported production markets.

Raw provider bet ID/name, raw selection, deterministic parsed line, odds, provider update
time, QuantLab capture time and classifier version are persisted only when the lab owner
is eligible for that fixture. GOAL rows may be stored across GOAL_SCOPE_V1; CARD, CORNER
and UNCLASSIFIED rows are stored only on CARDCORNER_TOP10_LEAGUES_V2 fixtures. Successful
odds responses also create a quantlab_market_captures watermark even when zero rows are
stored, so empty responses are not re-polled on every cycle or restart.

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

QuantLab has a hard daily ceiling of 1,000 API-Football requests under
quantlab_context. Configuration can lower this ceiling but cannot raise it.

A second shared-provider guard preserves production capacity. V1 defaults are:

- shared provider envelope: 7,500 requests/day;
- QuantLab production reserve: 1,500 requests/day;
- therefore QuantLab stops early if total shared usage has reached 6,000, even when its
  own 1,000-call allowance is not exhausted.

Priority order:

1. Discover the laboratory universe with global `/fixtures?date=...` shards rather than
   inheriting the narrower production Phase-I universe.
2. Persist shard success even when zero fixtures are returned; refresh date shards no more
   often than every six hours by default and include one prior UTC day for final statuses.
3. Reject out-of-scope competitions locally before any fixture-specific odds/context call.
4. Reuse already persisted production facts only as read-only historical fallback.
5. Derive zero-API features locally.
6. Reuse one all-market odds response across Bet365 and 1xBet, then persist only lab-
   eligible ownership classes.
7. Treat a successful empty/filtered odds response as a real capture for refresh gating.
8. Default odds refresh to 12 hours and standings refresh to 6 hours; automatic historical
   statistics backfill is disabled by default until a separately budgeted backfill is run.
9. Cache league/team/reference data.
10. Spend fixture-specific calls only when the hypothesis requires them.
11. Do not fetch completed-match statistics when referee coverage is absent.
12. Stop QuantLab before production operational capacity is endangered.

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


## GoalLab shadow decision contract

Task 002 evaluates persisted QuantLab GOAL observations without making provider requests.
It resolves the existing active Dixon-Coles artifact by exact API-Football
league/season/team-ID namespace through the validated production model loader, but never
writes model lifecycle state.

Only complete two-sided O/U 2.5 and BTTS captures are canonicalized in V1. PICK/PASS
decisions are append-only in quantlab_goal_decisions. Only PICK decisions may create a
quantlab_shadow_bets row. Decision and shadow IDs are deterministic so repeated runtime
cycles over unchanged evidence are idempotent.

The GoalLab decision stage runs even when the QuantLab provider daily ceiling has already
been reached, because it operates only on persisted observations and read-only model
artifacts.


## One-time fixture bootstrap

Migration 029 seeds a bounded current snapshot from already-persisted production
`fixtures` / `fixture_observations` only when a fixture has no QuantLab observation.
This bridge makes pre-existing QuantLab market observations evaluable without spending
provider calls during a daily API-ceiling event.

The bootstrap is not an ongoing discovery source and does not replace the independent
global QuantLab date-shard pipeline. Its rows are explicitly marked
`production-fixture-bootstrap`; subsequent provider-discovered QuantLab observations
remain authoritative for normal laboratory operation.
