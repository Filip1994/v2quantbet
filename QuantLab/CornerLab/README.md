# CornerLab

CornerLab owns QuantLab experiments for corner markets.

## Initial feature family

Planned structural features include:

- team corners for/against
- last-5 and last-10 corner form
- home/away corner splits
- total-corner mean and variance
- corner differential
- rest and fixture congestion
- selected attacking-pressure proxies when timestamp-safe

## League scope

CornerLab v1 shares CARDCORNER_STRONG_LEAGUES_V1 with CardLab. Fixture-specific
QuantLab provider spend is allowed only for the deterministic strong-league allowlist
in src/h2h/quantlab/scope.py.

Lower leagues, youth/academy, reserve and amateur competitions are rejected locally
before fixture-specific CornerLab requests. This is deliberate API-cost control rather
than a claim that corner markets can never exist outside the allowlist.

## Markets

For an eligible fixture, the shared raw collector retains every Bet365/1xBet market and
line returned by the provider. Corner ownership is versioned; unknown markets remain
UNCLASSIFIED. Canonical settlement support is added market by market.

## Referee variables

Referee card/foul variables do not belong to CornerLab v1.
