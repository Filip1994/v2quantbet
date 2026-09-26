# Task 003 — CornerLab + CardLab Shadow Pick Engines

Status: implementation branch `quantlab/task003-corner-card-engines`.

## Goal

Complete the first shadow-only probability/decision paths for CornerLab and CardLab
without changing GoalLab scope, production picks, bankroll, registration, or active
production model state.

## Shared safety contract

- Scope remains `CARDCORNER_TOP10_LEAGUES_V2`.
- Bet365 and 1xBet only, reusing already-persisted QuantLab market observations.
- No new provider request is made by either decision engine.
- Evaluation continues after the QuantLab daily API ceiling is reached.
- Every evaluated fixture produces append-only auditable PICK/PASS evidence.
- Only a newly-inserted PICK can create a row in `quantlab_shadow_bets`.
- Best available qualifying price wins per fixture/market/selection/line.
- Integer count lines are rejected in V1 because push handling is not yet canonicalized.
- Team-specific, handicap, half, race, booking-points, yellow-only and red-only markets
  are rejected by conservative market-name gates.

## CornerLab V1

Policy: `CORNERLAB_SHADOW_POLICY_V1`

Model: `CORNER_POISSON_FORM_V1`

The model reads historical `Corner Kicks` from already-stored
`quantlab_match_statistics_observations.raw_payload`.

For each target fixture:

1. require at least five historical matches with complete corner counts for each team;
2. prefer home-team home history and away-team away history when at least three such
   observations exist, otherwise fall back to the full recent sample;
3. calculate team corners-for and corners-against means;
4. expected home corners = mean(home-for, away-against);
5. expected away corners = mean(away-for, home-against);
6. total Poisson mean = expected home + expected away;
7. evaluate only complete two-sided half-count total-corners markets.

No historical corner value is fabricated when the stored provider payload is incomplete.

Default value thresholds:

- minimum edge: 4 percentage points;
- minimum EV: 4%;
- odds: 1.45–3.50;
- maximum quote age: 13 hours;
- minimum time to kickoff: 15 minutes;
- flat shadow stake: 10,000 minor units.

## CardLab V1

Policy: `CARDLAB_SHADOW_POLICY_V1`

Model: `CARD_REFEREE_POISSON_V1`

The numeric Poisson mean is the timestamp-safe `referee_card_rate` from
`CARDLAB_FEATURES_V1`.

Eligibility additionally requires:

- at least five referee card-history observations;
- at least five referee foul-history observations;
- available table-pressure context;
- available match-importance context.

The rivalry, pressure, importance and foul-rate values are persisted in decision details.
V1 intentionally does **not** invent coefficients that multiply those features into the
card mean. They remain eligibility/audit context until historical timestamp-safe labels
exist for calibration.

Default value thresholds:

- minimum edge: 5 percentage points;
- minimum EV: 5%;
- odds: 1.45–3.50;
- maximum quote age: 13 hours;
- minimum time to kickoff: 15 minutes;
- flat shadow stake: 10,000 minor units.

## Persistence

Migration `030_quantlab_corner_card_shadow_engines.sql` adds
`quantlab_count_decisions` for append-only CornerLab/CardLab PICK/PASS evidence and a
partial unique first-PICK guard.

Existing `quantlab_shadow_bets` remains the common shadow ledger.

## Dashboard

CornerLab and CardLab tabs show an upcoming fixture / decision pipeline containing the
latest PICK/PASS reason, model version, candidate, edge and EV. CardLab also retains its
feature/provenance table.

## Non-goals

- No GoalLab scope changes.
- No production decision writes.
- No automatic historical statistics backfill increase.
- No calibrated context coefficients for CardLab.
- No integer-line settlement/push logic.
- No team-specific corner/card markets in V1.
