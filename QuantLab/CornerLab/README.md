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

CornerLab v1 shares CARDCORNER_TOP10_LEAGUES_V2 with CardLab. The only eligible
domestic leagues are Premier League, La Liga, Serie A, Bundesliga, Ligue 1,
Eredivisie, Primeira Liga, Belgian Pro League, Süper Lig and Major League Soccer (MLS).

Lower divisions, cups, UEFA club competitions, youth/academy, reserve and amateur
competitions are rejected locally before fixture-specific CornerLab spend. This is
deliberate API-cost control rather than a claim that corner markets can never exist
outside the allowlist.

## Markets

The shared collector parses one all-market Bet365/1xBet payload. CORNER rows and
UNCLASSIFIED rows are persisted only for Top-10 fixtures; broad GoalLab-only fixtures
do not store corner-owned or unknown market rows. Canonical settlement support is added
market by market.

## Shadow Pick Engine V1

Task 003 adds `CORNERLAB_SHADOW_POLICY_V1` and `CORNER_POISSON_FORM_V1`.

The engine uses only already-stored completed-match `Corner Kicks` observations. It
requires at least five complete historical matches per team, prefers home/away venue
splits when at least three are available, derives expected home/away corner counts from
corners-for and corners-against means, and evaluates a Poisson total-count distribution.

Only complete two-sided half-count total-corner markets are eligible. Team totals,
handicaps, races, half markets and ambiguous integer lines are rejected. Default value
gates are edge >= 4 percentage points, EV >= 4%, odds 1.45-3.50, quote age <= 13 hours
and at least 15 minutes to kickoff.

No provider request is made by the decision engine itself. Missing history produces an
auditable PASS rather than a fabricated probability.

## Referee variables

Referee card/foul variables do not belong to CornerLab v1.
