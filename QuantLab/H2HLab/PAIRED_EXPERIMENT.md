# H2HLab paired experiment — DC-only vs DC+H2H

Status: **production shadow experiment**.

Experiment version: `H2HLAB_PAIRED_DC_VS_H2H_V1`.

## Question

The experiment tests one precise hypothesis:

> On the same H2H-eligible fixtures and the same market evidence, does adding direct
> head-to-head information to plain Dixon-Coles improve predictive quality and betting
> policy performance?

A strong H2H bucket by itself is not evidence for this hypothesis. The experiment must
compare plain DC and DC+H2H on identical frozen evidence.

## Experimental unit

One **fixture** is one paired experimental unit.

An experiment is frozen only once per fixture, at the first runtime evaluation where:

- direct H2H sample is at least 5;
- a plain Dixon-Coles model is available for the exact league/season;
- at least one O/U 2.5 or BTTS quote is execution-valid before model edge/EV gates;
- the quote is not from the future;
- quote age is at most 13 hours;
- kickoff is at least 15 minutes away;
- odds are inside 1.40–4.00.

Once frozen, the fixture is never re-randomized or re-evaluated with later odds. This avoids
post-outcome or market-movement cherry-picking.

## Arms

Both arms see the **same fixture, same H2H snapshot, same DC artifact, same bookmaker quote
pool, same timestamp and same execution gates**.

### Arm A — DC_ONLY

Probability:

    P_A = P_DC

Value metrics:

    edge_A = P_DC - P_market
    EV_A   = P_DC * odds - 1

A candidate qualifies when:

- edge >= 3 percentage points;
- EV >= 3%;
- all common execution gates pass.

The canonical DC-only bet is the qualifying candidate with the highest EV, then edge,
model probability, odds and deterministic bookmaker tie-break.

If none qualifies, the arm records `NO_BET`.

### Arm B — DC_H2H

Probability:

    P_B = w_DC * P_DC + w_H2H * P_H2H

The V1 weight schedule remains:

| Direct H2H N | DC | H2H |
|---:|---:|---:|
| 5 | 70% | 30% |
| 6 | 68% | 32% |
| 7 | 66% | 34% |
| 8 | 64% | 36% |
| 9 | 62% | 38% |
| 10+ | 60% | 40% |

The H2H component still uses recency × venue weighting and Beta(2,2) shrinkage.

Arm B uses the same edge/EV thresholds and the same canonical ranking as Arm A.

## Why this is paired

The experiment does **not** take an H2H-selected pick and retroactively ask what DC thought
about it. That would force both models to inherit the same realized bet and would make ROI
uplift meaningless.

Instead, each arm independently returns either:

- its own canonical `BET`; or
- `NO_BET`.

That allows H2H to change:

- whether a bet exists;
- the market;
- the side;
- the bookmaker/price selected by EV ranking.

## Frozen relation buckets

Each fixture is classified at freeze time:

- `SAME_BET` — exact same market, side and price;
- `SAME_SIDE_DIFFERENT_PRICE` — same market/side, different bookmaker or odds;
- `FLIP` — same market, opposite side;
- `DIFFERENT_MARKET` — both bet, but on different markets;
- `H2H_ONLY` — composite bets, DC-only does not;
- `DC_ONLY` — DC-only bets, composite does not;
- `BOTH_NO_BET`.

These are explanatory buckets, not success gates.

## Primary outcomes

### 1. ROI uplift

Each placed arm bet is settled at a flat 100.00-unit experimental stake.

For each arm:

    ROI = total P/L / total placed stake

Primary betting-policy effect:

    ROI uplift = ROI_DC+H2H - ROI_DC-only

A positive value means the H2H-aware policy is outperforming the plain-DC policy on the
same experimental universe.

### 2. Brier uplift

For predictive quality, every frozen fixture stores one binary probability trial per
supported market:

- O/U 2.5 scored as OVER 2.5 yes/no;
- BTTS scored as YES/NO.

For each trial:

    Brier_DC      = (P_DC - y)^2
    Brier_DC+H2H  = (P_composite - y)^2

where `y` is 0 or 1.

Primary probability effect:

    Brier uplift = mean(Brier_DC) - mean(Brier_DC+H2H)

Positive Brier uplift means DC+H2H is more accurate probabilistically.

This metric is deliberately independent of whether either arm placed a bet.

## Settlement explanation buckets

After the result is known, the experiment also records:

- `H2H_RESCUE` — only H2H bet and it won;
- `H2H_HARM` — only H2H bet and it lost;
- `H2H_RESCUE_FILTER` — H2H correctly suppressed a losing DC-only bet;
- `H2H_HARM_FILTER` — H2H suppressed a winning DC-only bet;
- `H2H_OUTPERFORM` — both bet and H2H arm produced higher P/L;
- `DC_OUTPERFORM` — both bet and DC-only produced higher P/L;
- `TIE`;
- `BOTH_NO_BET`.

These explain the ROI effect but do not replace the aggregate paired comparison.

## What counts as evidence

The experiment should be read in this order:

1. settled paired fixture N;
2. DC-only ROI vs DC+H2H ROI;
3. ROI uplift;
4. DC-only Brier vs DC+H2H Brier;
5. Brier uplift;
6. relation/outcome buckets explaining where the difference came from.

No single CONFIRM or CONFLICT bucket is sufficient to claim that H2H improves DC.

## Interpretation

The strongest evidence for the hypothesis is:

- positive ROI uplift at a meaningful settled N; and
- positive Brier uplift on the same experimental population.

If ROI improves while Brier worsens, H2H may be helping bet selection/thresholding rather
than the probability model itself.

If Brier improves while ROI does not, H2H may improve probability estimation without
creating exploitable market edge at the current gates/prices.

If both degrade, the H2H blend should be reduced or rejected rather than defended through
sub-bucket selection.

## Persistence

The experiment uses append-only tables:

- `quantlab_h2h_experiments` — frozen evidence and both arms;
- `quantlab_h2h_experiment_settlements` — final result, arm P/L and probability scores.

Schema migration:

- `060b_quantlab_h2h_paired_experiment.sql`.

The existing H2HLab shadow pick remains the DC+H2H operational shadow policy. The paired
experiment is an analytics layer and has no production betting authority.
