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

## Referee variables

Referee card/foul variables do not belong to CornerLab v1.

## Shadow Pick Engine V1

Task 003 adds `CORNERLAB_REFERENCE_POLICY_V1`.

The first CornerLab decision engine intentionally avoids inventing an untrained corner
model. It evaluates only persisted, complete two-sided full-match corner-total quotes on
half-lines. Bet365 and 1xBet must both quote the same provider bet and line. The opposite
bookmaker's proportional two-way de-vig probability is used as the independent shadow
reference probability.

A PICK requires at least 3 percentage points of edge and 3% EV, odds from 1.40 to 4.00,
quotes no older than 13 hours and at least 15 minutes to kickoff. At most one directional
PICK is retained per fixture/line/policy.

This evaluator makes zero provider requests and remains shadow-only.
