# H2HLab V1 — QuantLab policy and implementation

Status: **implemented as a fourth QuantLab program** alongside GoalLab, CornerLab and CardLab.

## Product placement

H2HLab is not nested inside GoalLab and does not create a third top-level QuantLab surface.
It appears in the two existing QuantLab cards/surfaces:

- **Dashboard → GoalLab / CornerLab / CardLab / H2HLab**
- **Analytics → GoalLab / CornerLab / CardLab / H2HLab**

The Dashboard is operational shadow-pick monitoring. Analytics is the historical/bucket layer used to test whether direct H2H information adds incremental value.

## V1 objective

H2HLab combines:

1. the currently active **plain Dixon–Coles** probability for the exact league/season/team scope; and
2. timestamp-safe **direct mutual-match H2H evidence** for the two teams.

GoalLab/DC+ authority is untouched. H2HLab loads the active production plain-DC artifact read-only and reuses QuantLab GOAL market observations already collected for BTTS and O/U 2.5.

## Frozen V1 policy

### Direct H2H sample

- hard minimum: **5 direct meetings**;
- maximum used: **10 latest direct meetings**;
- only terminal matches (FT, AET, PEN) before the target kickoff are eligible;
- only matches where the two provider team IDs are exactly the target pair are retained;
- future/scheduled matches are excluded.

### H2H weighting

Each meeting receives:

    final_weight = recency_weight × venue_weight

where:

- recency_weight = 0.90 ^ index (index 0 is the newest match);
- same home/away orientation as today's fixture: venue_weight = 1.00;
- reverse venue orientation: venue_weight = 0.75.

The weighted hit rate is then shrunk with a symmetric **Beta(2,2)** prior:

    P_H2H = (weighted_hits + 2) / (weighted_total + 4)

This prevents a small 5/5 sample from being treated as 100% probability.

### DC/H2H decision weights

The hard constraint is enforced: **Dixon–Coles may never carry more than 70% of the decision**.

| direct H2H N | DC weight | H2H weight |
|---:|---:|---:|
| 5 | 70% | 30% |
| 6 | 68% | 32% |
| 7 | 66% | 34% |
| 8 | 64% | 36% |
| 9 | 62% | 38% |
| 10+ | 60% | 40% |

Composite probability:

    P_final = w_DC × P_DC + w_H2H × P_H2H

A sample below 5 cannot create a H2HLab pick.

## V1 markets

V1 intentionally starts with markets directly supported by current plain DC mathematics and existing QuantLab GOAL quote capture:

- O/U 2.5: OVER, UNDER;
- BTTS: YES, NO.

This keeps the first H2H policy mathematically coherent and avoids inventing an H2H probability for unsupported market families.

## Quote/value gates

For every complete two-sided market pair, QuantLab de-vigs the market probability and computes edge = P_final − P_market and EV = P_final × odds − 1.

V1 PICK gates:

- H2H N >= 5;
- odds 1.40–4.00;
- quote age at most 13 hours;
- at least 15 minutes to kickoff;
- edge at least 3 percentage points;
- expected value at least 3%;
- maximum one canonical H2HLab exposure per fixture.

Qualified alternatives remain PASS decisions for auditability. Canonical ranking is expected value, then edge, composite probability, odds and deterministic bookmaker tie-break.

## Confirmation / conflict regimes

Every evaluated candidate records the relation between DC and H2H:

- **CONFIRM** — DC and shrunk H2H probability point to the same side of 50%;
- **CONFLICT** — they point to opposite sides;
- **NEUTRAL** — one side sits exactly on the boundary.

This classification is analytical evidence, not an extra hard gate in V1.

## Dashboard contract

H2HLab Dashboard reads the shared QuantLab shadow ledger with lab H2H. It shows the same operational fields as the other programs: match, market/selection, bookmaker, composite probability vs market probability, odds, edge, EV, result and timestamps.

H2HLab never writes production picks, production registration, bankroll state or active model state.

## Analytics contract

The Analytics H2H tab exposes the generic QuantLab performance/calibration cohorts plus dedicated H2H dimensions:

- direct H2H sample size;
- DC probability;
- shrunk H2H probability;
- DC decision weight;
- H2H decision weight;
- DC/H2H confirmation/conflict;
- H2H minus DC probability gap;
- crosses with market, selection, odds and composite probability.

The main V1 research question is **incremental value**: does the same DC probability regime perform better when direct H2H confirms it than when H2H is neutral or conflicts?

## Persistence

Migration 061_quantlab_h2hlab_v1.sql adds:

- H2H to the QuantLab shadow-lab check;
- immutable quantlab_h2h_snapshots;
- immutable quantlab_h2h_decisions with a database constraint DC weight <= 0.70 and H2H weight >= 0.30;
- one PICK per fixture/policy constraint.

H2H shadow settlement is V1 one-shot settlement on quantlab_shadow_bets, using final fixture evidence for O/U 2.5 and BTTS. Canceled/abandoned/awarded/walkover statuses void the exposure.

## API behavior

Direct history uses API-Football fixtures/headtohead with last=10. Snapshots are persisted and refreshed on a configurable cadence (QUANTBET_QUANTLAB_H2H_REFRESH_SECONDS, default six hours). Current odds are not recollected for H2HLab; the program reuses QuantLab GOAL market observations.

## Version identifiers

- policy: H2HLAB_DC_H2H_POLICY_V1
- display model: DC + H2H Composite
- snapshot id prefix: quantlab-h2h-snapshot-v1:
- decision id prefix: quantlab-h2h-decision-v1:
- settlement rule: H2HLAB_GOAL_MARKETS_SETTLEMENT_V1

## V1 non-goals

- H2H does not override or retrain Dixon–Coles.
- H2H does not modify GoalLab/DC+ picks.
- No 1X2/Double Chance H2H market is introduced until its probability/settlement policy is separately specified and backtested.
- No arbitrary confidence score is used as a gate; the auditable primitives are N, weighted/shrunk H2H probability, DC probability, weights, market probability, edge/EV and realized history.
