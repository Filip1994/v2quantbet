# QuantLab Architecture

## Repository structure

```text
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
├── goal_lab/
├── corner_lab/
└── card_lab/
```

## Services

Railway service: `quantbet-quantlab`.

The service uses the same PostgreSQL instance for shared immutable facts, but QuantLab writes only QuantLab-owned state. It must not write:

- `registered_picks`
- `pick_decisions`
- bankroll tables
- active production model state
- production registration policy

## Shared core

The QuantLab core owns:

- API budget accounting
- all-market Bet365/1xBet ingestion
- feature provenance conventions
- shadow-bet ledger
- settlement conventions
- P&L / ROI / CLV / drawdown reporting
- dashboard routing

## Lab ownership

### GoalLab
Owns goal probabilities and goal-market experiments, including DC+.

### CornerLab
Owns corner probabilities and corner-market experiments.

### CardLab
Owns card/foul probabilities and card-market experiments. Referee and match-context variables belong here unless a later experiment explicitly demonstrates a justified cross-lab use.

## Data contract

Every feature snapshot must eventually carry:

- `fixture_id`
- feature name
- feature value
- `source`
- `observed_at` / `available_at`
- feature version
- lab owner
- extraction/calculation version

No feature may use information that became available after the shadow decision timestamp.

## API policy

QuantLab has a hard daily ceiling of 1,000 API-Football requests under `quantlab_context`.

Priority order:

1. Reuse already persisted production facts.
2. Derive zero-API features locally.
3. Reuse one all-market odds response across Bet365 and 1xBet.
4. Cache league/team/reference data.
5. Spend fixture-specific calls only when the hypothesis requires them.
6. Stop QuantLab before production operational capacity is endangered.

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
