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

The shared QuantLab collector may receive multiple approved bookmakers in one all-market
payload, but CardLab persists CARD rows only from 1xBet (bookmaker ID 11).
CARDCORNER_MARKET_DRIVEN_V4 remains the fixture scope for senior men's football and
hard-rejects women's football before fixture-specific provider spend.

## Settlement warning

Provider markets such as cards, bookings and booking points can have different settlement
semantics. Raw provider bet ID/name/selection and line are preserved. No generic cards
settlement rule is assumed.

QuantLab is shadow-only and does not write production picks, bankroll or model state.

## Shadow Pick Engine / settlement authority

The current decision policy is `CARDLAB_1XBET_POISSON_POLICY_V5_MARKET80`.

V5 removes cross-book pricing from CardLab completely. A CardLab PICK requires only a
complete 1xBet `Cards Over/Under` half-line market and the timestamp-safe CardLab feature
snapshot.

The active probability model is `CARDLAB_REFEREE_POISSON_V1`:

- expected total cards (Poisson lambda) = historical `referee_card_rate`;
- minimum referee sample = five completed historical matches;
- OVER/UNDER probability is calculated directly from the Poisson distribution;
- 1xBet's own Over/Under pair is de-vigged to produce market probability;
- edge = model probability - 1xBet market probability;
- EV = model probability * 1xBet odds - 1.

Bet365 is not a CardLab input, reference bookmaker, PICK source or settlement source.
Foul rate, derby, table pressure and match importance remain persisted CardLab context for
later measured model upgrades, but V5 does not assign arbitrary weights to them.

Yellow-only, red-only, bookings and booking-points markets remain excluded. The canonical
PICK market is API-Football bet ID 80, `Cards Over/Under`, on 1xBet only.

### Current settlement status

1xBet settlement is reproduced from `/fixtures/events`: regular time including stoppage
time, extra time excluded, player card events only, with a player's contribution capped at
two cards so a second-bookable dismissal cannot be double-counted. Card event observations
and settlement events are append-only.
