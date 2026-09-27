# CardLab

CardLab owns QuantLab experiments for cards, bookings and fouls.

## CardLab v1

CardLab v1 immediately uses five timestamp-safe match-context variables:

1. referee_card_rate
2. referee_foul_rate
3. derby_rivalry_indicator
4. table_pressure
5. match_importance

The exact V1 formulas, provenance requirements and leakage rules are frozen in
[FEATURES_V1.md](./FEATURES_V1.md).

## Research scope

CardLab now uses `CARDCORNER_MARKET_DRIVEN_V4`.

There is no Top-10 competition gate. Women's football is a global hard exclusion. For
remaining fixtures, QuantLab discovers the broad universe and CARD markets are retained
wherever the provider publishes them.

Target referee/standings/context calls are then made only for fixtures that actually have
persisted CARD market evidence. Historical completed-match statistics backfill is broad
because cards/fouls also feed model research and cross-lab feature engineering.

Ambiguous card semantics (for example booking points vs card counts, team-only cards,
halves, handicaps) remain research-only until explicitly canonicalized.

## Separation

These five context variables are CardLab-owned in v1. They are not inputs to GoalLab/DC+
or CornerLab unless a later separately-versioned experiment explicitly tests that change.

## Market ingestion

The shared QuantLab collector parses one returned Bet365/1xBet all-market payload, but
CARD and UNCLASSIFIED rows are persisted only when the fixture passes
CARDCORNER_MARKET_DRIVEN_V4. That scope is market-driven for senior men's football but
hard-rejects women's football before fixture-specific provider spend.

## Settlement warning

Provider markets such as cards, bookings and booking points can have different settlement
semantics. Raw provider bet ID/name/selection and line are preserved. No generic cards
settlement rule is assumed.

QuantLab is shadow-only and does not write production picks, bankroll or model state.

## Shadow Pick Engine / settlement authority

The current decision policy is `CARDLAB_REFERENCE_CONTEXT_POLICY_V3_1XBET_ONLY`.

The previous policies could identify value candidates before CardLab had a canonical
sportsbook settlement contract. V3 is 1xBet-only for PICK registration: 1xBet is the
target/settled bookmaker, while Bet365 may be used only as an independent fair-price
reference for the existing cross-book probability model.

The CardLab evaluator uses the same conservative cross-book fair-reference mechanism as
CornerLab for supported full-match total-card half-lines, then requires timestamp-safe
CardLab context before a PICK is possible.

V1 requires `referee_card_rate` with at least five historical matches. OVER is admitted
only when the referee rate is above the offered line; UNDER only when it is below. Foul
rate, derby, table pressure and match importance are preserved in decision evidence but
are not assigned invented probability weights.

Yellow-only, red-only, bookings and booking-points markets are rejected in V1 because
their settlement semantics are not interchangeable with the aggregate referee card-rate
feature.

The evaluator adds zero provider requests and writes only QuantLab decision/shadow tables.

### Current settlement status

API-Football's pre-match catalog identifies bet ID 119 as `Total Cards`. Under V3,
only bookmaker ID 11 (1xBet) is PICK-authorized. Bet365 is reference-only.

1xBet settlement is reproduced from `/fixtures/events`: regular time including stoppage
time, extra time excluded, player card events only, with a player's contribution capped at
two cards so a second-bookable dismissal cannot be double-counted. Card event observations
and settlement events are append-only.
