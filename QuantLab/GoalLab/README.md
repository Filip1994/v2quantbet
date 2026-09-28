# GoalLab

GoalLab is QuantLab's isolated pre-match goals/BTTS research system.

It does **not** write production registered picks, production bankroll state or production
model activation state.

## Current model

The pick-producing research model family is:

- model: **DC+ Pro Structural**
- model prefix: `DC_PLUS_PRO_STRUCTURAL_V1:`
- feature version: `GOALLAB_DC_PLUS_STRUCTURAL_FEATURES_V1`
- evaluation policy: `GOALLAB_DC_PLUS_STRUCTURAL_POLICY_V2`
- canonical pick policy: `GOALLAB_DC_PLUS_PICK_POLICY_V1`
- settlement rule: `GOALLAB_SETTLEMENT_V1`

Plain production Dixon-Coles remains a read-only control under
`GOALLAB_CONTROL_POLICY_V2`. It has no GoalLab PICK authority.

## What DC+ does

DC+ preserves the Dixon-Coles score model:

```
log(lambda_home) =
    intercept
  + home_advantage
  + home_attack
  + away_defence
  + league_effect
  + learned_home_structural_offset

log(lambda_away) =
    intercept
  + away_attack
  + home_defence
  + league_effect
  + learned_away_structural_offset
```

The Dixon-Coles `rho` correction remains for 0-0, 0-1, 1-0 and 1-1.

Structural offsets are learned with ridge regularization. Bookmaker odds, API-Football
`/predictions`, target-match live statistics and hand-written football-effect
coefficients are not DC+ Structural probability inputs.

Model identity is data/feature/parameter driven rather than wall-clock driven. The exact
training evidence plus model/feature hyperparameters is fingerprinted. If that fingerprint
matches an existing immutable artifact, GoalLab reloads the artifact and does not run the
optimizer again. A changed fingerprint is the explicit retrain boundary and produces a new
model identity; decision time alone never triggers a retrain.

## Structural feature contract

The canonical 305-variable registry is in
[DC_PLUS_PRO_V1.md](./DC_PLUS_PRO_V1.md).

Every model artifact persists:

- exact active model feature names;
- base feature names;
- feature means/scales;
- contract block coverage;
- training sample/history counts;
- parameters and regularization settings;
- source/provenance rules.

The GoalLab dashboard renders the **exact active feature names for the current artifact**.
This matters because a contract block can exist in code while sparse provider coverage can
still keep a concrete feature out of a particular fitted artifact.

Implemented Structural blocks include:

- Base DC / reliability;
- recent goals/results/form;
- venue form;
- season and league-normalized strength;
- shots, SOT, inside-box and conversion proxies;
- finishing / goalkeeper proxies;
- possession and passing;
- corners / territorial proxies;
- historical discipline;
- rest and congestion;
- timestamp-safe standings;
- timestamp-safe injury/suspension counts;
- historical projected-player form from prior completed `/fixtures/players` captures;
- manager/coach context;
- H2H;
- opponent-adjusted form;
- regularized matchup interactions;
- explicit missingness/coverage indicators.

Target lineup/formation is intentionally **not silently mixed into Structural DC+**.
It remains a separately versioned Late-Lineup layer because lineups are normally published
close to kickoff.

## Timestamp / leakage rules

For a target prediction:

- only completed earlier matches can enter rolling historical features;
- target-match live statistics/events/players never enter a pre-match prediction;
- standings, injuries and manager context must have `available_at <= decision_at`;
- target lineup, if used later, belongs to the separate late layer;
- every target feature snapshot retains provenance and the exact model version.

Historical player projection uses only player appearances before the target kickoff.
The target fixture's `/fixtures/players` response is never used to build its own features.

## Canonical markets

GoalLab currently evaluates only markets with explicit settlement semantics:

- O/U 2.5 — OVER / UNDER;
- BTTS — YES / NO.

A quote is evaluable only when both complementary selections from the **same bookmaker
and capture** are present.

Market fair probability is proportional two-way de-vig.

## Candidate gates

A candidate must satisfy all of:

- edge >= 3 percentage points;
- expected value >= 3%;
- odds 1.40 through 4.00;
- quote age <= 13 hours;
- kickoff at least 15 minutes away.

Odds are used only after DC+ has produced sports probabilities.

## How one GoalLab pick is chosen

Research evidence and actual GoalLab picks are separate concepts.

1. DC+ evaluates every canonical market/selection/eligible bookmaker.
2. For the same market/selection, the best qualifying price is retained.
3. All remaining qualifying candidates for the fixture are ranked by:
   1. expected value;
   2. edge;
   3. model probability;
   4. odds;
   5. deterministic market/selection/bookmaker tie-break.
4. Exactly **one canonical GoalLab pick per fixture/pick-policy version** may be persisted.
5. All other evaluated candidates remain immutable decision evidence.

The pick stores the exact source decision and feature snapshot, so it is always possible
to reconstruct why that pick existed.

Flat research stake is 10,000 minor units.

## Pick authority gate

`QUANTBET_QUANTLAB_GOAL_PICK_AUTHORITY` is an explicit manual authority request and
defaults to OFF. `QUANTBET_QUANTLAB_GOAL_APPROVED_MODEL_VERSION` must also equal the
**exact immutable DC+ model hash** being evaluated.

Even when authority is requested ON, the engine will not create a GoalLab pick unless the
exact approved model version has:

- a recorded chronological DC-vs-DC+ holdout;
- a PASS leakage audit;
- enough common holdout coverage for manual review;
- `authority_review_status = READY_FOR_MANUAL_REVIEW`.

Validation does not automatically promote a model. The metrics are evidence for the
explicit authority decision. When new data produces a different model hash, pick creation
pauses until that new hash is explicitly approved.

## Dedicated GoalLab Picks sector

Canonical picks live in `quantlab_goal_picks`, separate from generic QuantLab shadow
research rows.

Each pick stores:

- source DC+ decision ID;
- exact feature snapshot ID;
- model and policy versions;
- bookmaker and entry quote evidence;
- market / selection / line;
- model probability and de-vig market probability;
- edge and EV;
- `lambda_home`, `lambda_away` and `rho`;
- flat stake;
- number of qualifying candidates;
- the complete candidate ranking payload.

The table is append-only.

## Settlement and results

Settlements live in the separate append-only
`quantlab_goal_pick_settlements` table.

Settlement uses the shared stable result pipeline only when
`fixture_result_acquisition_states.phase = COMPLETE`.

Rules:

- O/U 2.5 uses regulation total goals;
- BTTS uses regulation goals;
- non-played voidable terminal fixtures settle VOID;
- WIN P&L = stake × (odds - 1);
- LOSS P&L = -stake;
- VOID P&L = 0.

Every settlement retains the exact result observation used.

## DC+ validation

Each immutable model artifact may receive one
`GOALLAB_CHRONOLOGICAL_HOLDOUT_V3` validation record. V1/V2 evidence remains immutable and queryable.

The chronological holdout compares DC+ Structural against plain Dixon-Coles on the same
common evaluation fixtures. It prefers league-specific controls and uses a pooled
sparse-latent plain-DC fallback where league-specific control coverage is unavailable.
The pooled control keeps all chronological training matches, estimates latent attack/defense
only for teams with sufficient history, and assigns neutral zero effects to sparse teams,
and records:

- exact-score mean/total log likelihood;
- home/away goal MAE;
- total-goals MAE/RMSE;
- Over 2.5 Brier score and calibration mean;
- BTTS Brier score and calibration mean;
- common evaluation sample size;
- leakage checklist;
- DC+ minus DC metric deltas.

No unrecorded automatic “winner” rule grants pick authority.

## GoalLab dashboard

The Goal tab is the operational surface for:

- current DC+ model/version;
- exact active variables;
- contract coverage by feature block;
- validation status and DC+ vs DC metrics;
- upcoming DC+ decision pipeline;
- canonical GoalLab picks only;
- pending/WIN/LOSS/VOID settlement state;
- P&L / ROI and model probabilities.

GoalLab Analytics V2 is the read-only research/audit surface. It reports:

- model, policy, market/selection, bookmaker, league and weekly cohorts;
- selected-pick Brier score, binary log loss and calibration bins;
- realized same-book/same-market pre-kickoff CLV where later immutable quotes exist;
- flat-stake max drawdown;
- canonical-pick integrity checks for duplicate fixture/policy keys, source-decision
  provenance, feature payloads, model identity and valid probabilities;
- exact model and pick drilldowns for reproducibility.

Closing evidence is derived from the latest matching immutable GoalLab market observation
after the entry quote and strictly before kickoff. It is research evidence only and is
never a probability-model input.

CornerLab and CardLab remain separate labs and are not part of GoalLab pick semantics.

## Scope

GoalLab uses `GOAL_SCOPE_V2`.

The independent QuantLab fixture inventory is discovered from API-Football date shards,
then Goal scope is applied locally. Women's football remains globally hard-blocked from
QuantBet/QuantLab.

See also:

- [API-Football Research Catalog](./API_FOOTBALL_RESEARCH_CATALOG.md)
- [DC+ Pro V1 contract](./DC_PLUS_PRO_V1.md)
