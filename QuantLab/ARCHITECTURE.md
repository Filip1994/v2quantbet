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
- all-market Bet365/1xBet ingestion
- versioned zero-request league eligibility
- feature provenance conventions
- shadow-bet ledger
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
restricted by CARDCORNER_STRONG_LEAGUES_V1.

### CardLab

Owns card/foul probabilities and card-market experiments. Referee and match-context
variables belong here unless a later experiment explicitly demonstrates a justified
cross-lab use. Fixture-specific spend is restricted by CARDCORNER_STRONG_LEAGUES_V1.

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

QuantLab-owned Task 001 tables are append-only:

- quantlab_market_observations
- quantlab_fixture_context_observations
- quantlab_match_statistics_observations
- quantlab_standings_snapshots
- quantlab_card_feature_snapshots

## Market collector contract

The QuantLab collector requests one pre-match /odds?fixture=<id> payload and reuses it
for both Bet365 (8), 1xBet (11) and all laboratory classifiers. It does not use the
production canonical adapter that limits supported production markets.

Raw provider bet ID/name, raw selection, deterministic parsed line, odds, provider update
time, QuantLab capture time and classifier version are persisted. Unknown markets are
retained as UNCLASSIFIED.

## API policy

QuantLab has a hard daily ceiling of 1,000 API-Football requests under
quantlab_context. Configuration can lower this ceiling but cannot raise it.

A second shared-provider guard preserves production capacity. V1 defaults are:

- shared provider envelope: 7,500 requests/day;
- QuantLab production reserve: 1,500 requests/day;
- therefore QuantLab stops early if total shared usage has reached 6,000, even when its
  own 1,000-call allowance is not exhausted.

Priority order:

1. Reuse already persisted production facts.
2. Reject out-of-scope leagues locally for zero API cost.
3. Derive zero-API features locally.
4. Reuse one all-market odds response across Bet365 and 1xBet.
5. Cache league/team/reference data.
6. Spend fixture-specific calls only when the hypothesis requires them.
7. Do not fetch completed-match statistics when referee coverage is absent.
8. Stop QuantLab before production operational capacity is endangered.

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
