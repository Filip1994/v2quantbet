# QuantBet Architecture

_Last synchronized: 2026-09-30_

## Top-level sectors

```text
                         PostgreSQL
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
     Production          Research           QuantLab
          │                  │                  │
 live decisions       read-only final-   Goal / Corner /
 bankroll/risk        gate analytics       Card labs
```

## Production

Production owns:

- fixture discovery;
- trusted historical model training;
- active model lifecycle;
- odds ingestion;
- prediction/value;
- eligibility/risk/final quote verification;
- pick registration;
- monitoring/closing;
- settlement/bankroll;
- bulletin;
- operator controls.

Railway PostgreSQL is canonical. SQLite is not a production fallback.

## Research

Research reads durable Production evidence and maintains the comparable final-gate analytical universe.

It may compute cohorts, buckets, counterfactual flat-stake results and CLV analytics, but it must not mutate Production.

## QuantLab

QuantLab independently discovers/collects broader research data and owns its own QuantLab tables.

It must not write Production registered picks, Production bankroll, Production decision records or active Production model state.

Laboratories:

- GoalLab — DC+ Structural;
- CornerLab — pressure-Poisson;
- CardLab — referee-Poisson.

## Provider/API boundary

API-Football identities are validated before provider responses become canonical business evidence.

All services share the provider request envelope; QuantLab usage remains separately attributable.

## Evidence principles

- append-only where facts must remain auditable;
- timestamp-safe feature availability;
- no post-kickoff data in pre-match decisions;
- exact model/policy/version provenance;
- immutable decision evidence;
- same-book closing where possible.

## Runtime/services

The current Railway footprint includes separate Production, dashboard/research/QuantLab services plus PostgreSQL. One-shot diagnostic services should be removed or explicitly marked so the production topology remains legible.

## Release boundary

GitHub CI and Railway deployment state are independent facts.

Target release path:

```text
Git commit → CI PASS → exact SHA deploy → runtime SHA visibility
```

See [CURRENT_PRIORITIES.md](./CURRENT_PRIORITIES.md).
