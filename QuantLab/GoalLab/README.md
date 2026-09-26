# GoalLab

GoalLab owns QuantLab experiments for goals and BTTS.

## Initial model family

DC+ Core keeps current Dixon-Coles as the control/base and tests incremental structural
features:

- recent goals for/against
- recent points/form
- home/away splits
- rest-day differential
- fixture congestion

Market-aware variants must be evaluated separately from structural DC+ so that market
information is not silently mixed into an independent sports probability model.

## League scope

GoalLab uses GOAL_SCOPE_V1 and intentionally has a much broader universe than CardLab
and CornerLab.

Eligible by default: professional senior competitions not explicitly excluded.

GoalLab no longer inherits production Phase-I fixture discovery. QuantLab first captures
global API-Football date shards into its own fixture inventory, then applies GOAL_SCOPE_V1
locally. This is what allows GoalLab to retain lower professional leagues that production
may intentionally ignore.

Excluded locally before fixture-specific QuantLab requests:

- youth competitions U5 through U23 and equivalent Under labels;
- academy, reserve/reserves and amateur/amateurs competitions;
- reserve-team suffixes such as B and II where detected by the deterministic rule;
- all African countries plus competitions explicitly identified as CAF/Africa;
- Far East countries in the V1 region registry: Brunei, Cambodia, China, Chinese Taipei,
  Hong Kong, Indonesia, Japan, Laos, Macau/Macao, Malaysia, Mongolia, Myanmar, North
  Korea, Philippines, Singapore, South Korea/Korea Republic, Taiwan, Thailand,
  Timor-Leste and Vietnam.

The scope is versioned in src/h2h/quantlab/scope.py. Scope changes require documentation
and a new/updated version rather than ad-hoc runtime inference.

## Markets

For every GOAL_SCOPE_V1 fixture, the shared collector parses the provider response but
persists only markets classified as GOAL unless the fixture also passes
CARDCORNER_TOP10_LEAGUES_V2. UNCLASSIFIED markets are therefore not retained on broad
GoalLab-only fixtures; this prevents unknown card/corner markets from bypassing the
Top-10 storage gate. Canonical modeling and settlement support remain explicit and
versioned.

## Shadow Pick Engine V1

Task 002 introduces `GOALLAB_SHADOW_POLICY_V1` as the first end-to-end shadow decision
engine.

The control probability source is the existing validated active Dixon-Coles artifact for
the exact league/season. QuantLab reads that artifact but cannot activate, retrain or
mutate production model state.

V1 evaluates only complete two-sided:

- O/U 2.5 — OVER / UNDER;
- BTTS — YES / NO.

Market fair probability is proportional two-way de-vig. Default shadow gates are:

- edge >= 3 percentage points;
- expected value >= 3%;
- odds 1.40 through 4.00;
- quote age <= 13 hours;
- kickoff at least 15 minutes away;
- flat shadow stake 10,000 minor units.

If model coverage or a complete market is absent, the engine records PASS rather than
inventing data. The GoalLab dashboard includes an upcoming-fixture decision pipeline with
scope, odds-capture, model, candidate and PASS/PICK reason.

This evaluator makes no provider requests. It can run on persisted quotes even when the
daily QuantLab API ceiling is already exhausted.

## Referee variables

Referee card/foul variables do not belong to GoalLab v1.


## Shadow decision engine

Task 002 adds GOALLAB_SHADOW_POLICY_V1 as the first executable GoalLab shadow-pick
pipeline.

The control model is the already-active, validated API-Football Dixon-Coles artifact for
the fixture's exact league and season. QuantLab reads that model only; it does not train,
activate or mutate production model state.

Task 002 canonical markets are intentionally narrow:

- O/U 2.5 (provider bet 5): OVER / UNDER;
- BTTS (provider bet 8): YES / NO.

A market is evaluable only when both complementary selections from the same bookmaker and
capture are present. Market fair probability uses proportional two-way de-vig. The engine
records every evaluated outcome as PICK or PASS with an explicit reason. Missing active
model, missing team coverage, incomplete markets, stale quotes and policy failures remain
visible rather than being converted into synthetic probabilities.

GOALLAB_SHADOW_POLICY_V1 defaults:

- minimum edge: 3 percentage points;
- minimum expected value: 3%;
- odds: 1.40–4.00;
- maximum quote age: 13 hours;
- minimum time to kickoff: 15 minutes;
- flat shadow stake: 10,000 minor units.

When multiple supported bookmakers qualify for the same market/selection/evidence cycle,
only the best available price becomes a shadow PICK. These thresholds are laboratory
controls only and do not alter production registration policy.
