# Task 003 — CornerLab + CardLab Shadow Pick Engines

> **Superseded scope note (2026-09-26):** the historical Top-10 budget gate described below was replaced by `CARDCORNER_MARKET_DRIVEN_V3` after the football provider budget increased to 75,000 requests/day. The remainder of this file records the implementation contract as it existed at the time.

Status: implementation branch.

## Objective

Complete the next two QuantLab shadow-only decision paths without changing GoalLab scope
and without adding provider requests.

1. CornerLab: produce auditable shadow decisions from persisted Bet365/1xBet corner totals.
2. CardLab: produce auditable shadow decisions from persisted card totals, with the
   existing timestamp-safe CardLab referee/context snapshot acting as a conservative gate.

Production prediction, registration, bankroll and active-model state remain out of scope.

## Scope

Both engines run only inside `CARDCORNER_TOP10_LEAGUES_V2`:

- Premier League
- La Liga
- Serie A
- Bundesliga
- Ligue 1
- Eredivisie
- Primeira Liga
- Belgian Pro League / Jupiler Pro League
- Süper Lig
- Major League Soccer

No scope expansion is part of this task.

## Provider-cost rule

Task 003 adds **zero provider requests**. It evaluates only already-persisted:

- `quantlab_market_observations`
- `quantlab_card_feature_snapshots`

Collection/context behavior remains owned by Task 001.

## Supported market shape

V1 supports only conservative, two-sided full-match total markets:

- lab owner is CORNER or CARD;
- same bookmaker / provider bet / capture / line;
- exactly one `OVER` and one `UNDER` selection;
- half lines only (`x.5`) so pushes are impossible;
- team, half, handicap, race, exact, range, odd/even and Asian variants are rejected.

Card V1 also rejects yellow-only, red-only, bookings and booking-points market names
because their settlement semantics do not match the existing aggregate referee card rate.

## Probability source

No untrained statistical coefficients are fabricated.

For each supported target quote, the model probability is the proportional two-way
de-vig fair probability from the *other* supported bookmaker on the same provider bet
and line.

If Bet365 and 1xBet do not both provide a complete compatible quote, the engine records
`PASS / NO_INDEPENDENT_REFERENCE_BOOK`.

The model identifiers are:

- CornerLab: `CROSS_BOOK_FAIR_REFERENCE_V1`
- CardLab: `CROSS_BOOK_FAIR_REFERENCE_CARD_CONTEXT_V1`

This is a shadow reference/value model, not a claim that bookmaker consensus is a
fully trained predictive model. Its calibration can be measured before any future
production consideration.

## CardLab context gate

CardLab additionally requires the latest timestamp-safe `CARDLAB_FEATURES_V1` snapshot.

Hard V1 requirements:

- `referee_card_rate` is available;
- `referee_sample_size >= 5`;
- the referee rate supports the proposed direction:
  - OVER only if referee_card_rate > line;
  - UNDER only if referee_card_rate < line.

The remaining CardLab context fields (foul rate, derby, table pressure and match
importance) are persisted in the decision evidence for analysis; V1 does not invent
untrained probability coefficients for them.

## Value policy

Both labs use:

- minimum edge: 3 percentage points;
- minimum EV: 3%;
- odds range: 1.40–4.00;
- maximum age of target/reference quote: 13 hours;
- minimum time to kickoff: 15 minutes;
- flat shadow stake: 10,000 minor units.

At most one PICK is retained per fixture/lab/market/line/policy. If multiple directions
or bookmakers qualify, the engine deterministically chooses the highest EV, then edge,
then odds.

## Audit ledger

Migration 030 adds append-only `quantlab_context_market_decisions` for both PICK and PASS.

Evidence includes:

- target and reference bookmaker;
- provider bet identity;
- target/reference two-sided observation IDs;
- target/reference quote timestamps and odds;
- de-vig market probability;
- reference/model probability;
- edge and EV;
- CardLab context snapshot when applicable;
- deterministic evidence fingerprint;
- policy/model versions and reason.

Only a newly inserted PICK may create a `quantlab_shadow_bets` row.

## Runtime

CornerLab and CardLab evaluation runs outside the provider collection-budget block, just
like GoalLab Task 002. Existing persisted evidence can therefore be evaluated even after
the daily QuantLab API ceiling is reached.

## Non-goals

- no GoalLab scope changes;
- no new provider endpoint;
- no production pick registration;
- no bankroll mutation;
- no trained corner regression/Poisson model in this task;
- no unvalidated CardLab feature weights.
