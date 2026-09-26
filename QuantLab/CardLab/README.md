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

## League scope

CardLab v1 uses CARDCORNER_TOP10_LEAGUES_V2. Fixture-specific provider calls are
allowed only for ten domestic top flights implemented in src/h2h/quantlab/scope.py:

- England — Premier League
- Spain — La Liga
- Italy — Serie A
- Germany — Bundesliga
- France — Ligue 1
- Netherlands — Eredivisie
- Portugal — Primeira Liga
- Belgium — Jupiler Pro League / Pro League
- Turkey/Türkiye — Süper Lig
- USA — Major League Soccer (MLS)

Lower divisions, cups, UEFA club competitions, youth/academy, reserve and amateur
competitions are rejected locally before CardLab context/statistics spend. The purpose
is API discipline and predictable referee/card-data coverage, not a claim that card
markets cannot exist elsewhere.

## Separation

These five context variables are CardLab-owned in v1. They are not inputs to GoalLab/DC+
or CornerLab unless a later separately-versioned experiment explicitly tests that change.

## Market ingestion

The shared QuantLab collector parses one returned Bet365/1xBet all-market payload, but
CARD rows are persisted only when the fixture passes CARDCORNER_TOP10_LEAGUES_V2.
UNCLASSIFIED rows are retained only on Top-10 fixtures so unknown card/corner-like
markets cannot leak into broad GoalLab-only storage.

## Settlement warning

Provider markets such as cards, bookings and booking points can have different settlement
semantics. Raw provider bet ID/name/selection and line are preserved. No generic cards
settlement rule is assumed.

QuantLab is shadow-only and does not write production picks, bankroll or model state.
