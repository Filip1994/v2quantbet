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

CardLab v1 uses CARDCORNER_STRONG_LEAGUES_V1. Fixture-specific provider calls are
allowed only for the strong-league allowlist implemented in src/h2h/quantlab/scope.py.

This intentionally excludes lower leagues such as Poland III Liga, youth/academy,
reserve and amateur competitions before any CardLab context/statistics request is made.
The V1 allowlist includes major UEFA club competitions and selected strong domestic
leagues across Europe plus Brazil, Argentina, MLS and Liga MX.

The purpose is API discipline: card/referee data quality and market availability are
not assumed outside leagues where the laboratory has explicitly chosen to spend budget.

## Separation

These five context variables are CardLab-owned in v1. They are not inputs to GoalLab/DC+
or CornerLab unless a later separately-versioned experiment explicitly tests that change.

## Market ingestion

The shared QuantLab collector still preserves all returned Bet365/1xBet raw markets for
an eligible fixture. CardLab ownership is assigned only by the versioned market
classifier. Unknown provider markets are retained as UNCLASSIFIED rather than discarded.

## Settlement warning

Provider markets such as cards, bookings and booking points can have different settlement
semantics. Raw provider bet ID/name/selection and line are preserved. No generic cards
settlement rule is assumed.

QuantLab is shadow-only and does not write production picks, bankroll or model state.
