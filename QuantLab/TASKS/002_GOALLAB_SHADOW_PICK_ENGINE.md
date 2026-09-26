# Task 002 — GoalLab Shadow Pick Engine + Fixture Decision View

Status: implementation in progress.

## Objective

Turn already-collected QuantLab fixtures and GOAL market observations into auditable,
shadow-only GoalLab decisions without changing production prediction, registration,
bankroll or staking behavior.

Task 002 must not add provider calls. It consumes persisted QuantLab data plus the
already-active production Dixon-Coles artifact as a read-only control model.

## Scope

### Part A — GoalLab control model

For each upcoming GOAL_SCOPE_V1 fixture with league/season/team IDs:

1. Resolve the currently active API-Football Dixon-Coles model for the same league and
   season through the existing validated model-loader boundary.
2. Never mutate or activate production model state.
3. If no active model exists or either team is absent from that model, record an explicit
   PASS reason. Never fabricate a probability.
4. Supported Task 002 markets are the canonical control pair only:
   - provider bet 5, O/U 2.5 — OVER / UNDER;
   - provider bet 8, BTTS — YES / NO.

### Part B — Market probability and value arithmetic

Only complete two-sided quotes from the same fixture, bookmaker, provider bet and capture
timestamp are eligible.

For each side:

- raw implied probability = 1 / odds;
- two-way market probability = selected raw implied / sum of both raw implied;
- edge = model probability - market probability;
- expected value = model probability * odds - 1.

No single-sided devig or inferred companion price is allowed.

### Part C — Shadow policy

Policy identifier: GOALLAB_SHADOW_POLICY_V1.

Default controls:

- minimum edge: 3 percentage points;
- minimum EV: 3%;
- odds range: 1.40 through 4.00;
- maximum quote age: 13 hours;
- minimum time to kickoff: 15 minutes;
- flat shadow stake: 10,000 minor units.

When more than one bookmaker qualifies for the same market/selection/evidence cycle,
only the highest-odds quote is written as a PICK. Other qualifying books are PASS with
reason BETTER_PRICE_AVAILABLE.

These are experiment thresholds, not production registration thresholds.

### Part D — Decision ledger and shadow bets

Add append-only QuantLab-owned decision records containing:

- fixture/model/policy provenance;
- bookmaker and raw-provider market identity where available;
- canonical market/selection;
- quote pair evidence;
- model probability;
- market probability;
- edge and EV;
- PICK/PASS;
- explicit reason and JSON details.

Only PICK decisions write to quantlab_shadow_bets. All IDs are deterministic and writes
are idempotent.

No writes are permitted to production quote_series, value_evaluations, pick_decisions,
registered_picks, bankroll or active model tables.

### Part E — Upcoming fixture decision view

GoalLab dashboard adds a read-only upcoming-fixture pipeline table showing:

- fixture and kickoff;
- GoalLab eligibility;
- Card/Corner eligibility;
- latest market-capture time;
- latest GoalLab decision;
- decision reason;
- active model version where available.

The view performs no provider requests.

## API cost

Task 002 adds zero API-Football requests. It operates on persisted QuantLab market data and
read-only production model artifacts.

## Leakage / provenance

Decision time must be before kickoff. Market observations must have been captured no later
than decision time. The active model is resolved at decision time and its exact immutable
model_version_id is stored. No future result or post-kickoff information is used.

## Definition of done

- deterministic GoalLab decision engine implemented;
- explicit PASS reasons for missing model/coverage/quotes and policy rejection;
- valid PICKs insert into quantlab_shadow_bets;
- upcoming fixture pipeline is visible read-only on GoalLab;
- Task 002 creates no provider request path;
- full CI passes;
- QuantLab documentation/worklog updated;
- Railway QuantLab deployment reaches SUCCESS.
