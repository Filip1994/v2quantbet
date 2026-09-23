# QuantBet

QuantBet is a pre-match football value-betting engine.

## Architecture

- **GitHub** — source code, version control, tests and CI.
- **Railway engine service** — live production worker deployment of `main`, using the single-leader scheduler entrypoint `python -m h2h.entrypoint`.
- **Railway PostgreSQL** — canonical durable state store for fixtures, quote history, model/runtime state, decisions, registered picks, monitoring, settlement/accounting and bulletin projections.
- **Read-only HTTP surfaces** — liveness/readiness plus an authenticated dashboard route on the production service, with a separate dashboard-only entrypoint for operational independence.

The engine is strictly pre-match. It records and evaluates quote observations before kickoff and does not process live/in-play betting opportunities.

## Development principles

- Quantitative model mathematics is regression-tested before infrastructure changes.
- Odds are acquired through canonical, provider-neutral interfaces.
- PostgreSQL is the production source of truth.
- Historical quote, pick, closing, settlement and bankroll facts are treated as durable/auditable records rather than mutable UI state.
- No production implementation is accepted without passing tests.
- Changes are implemented in small, verifiable functional increments.
- Secrets belong in the local environment or Railway variables, never in Git.

## Current production status

As of **2026-09-23**, the Railway production service is deployed from `Filip1994/v2quantbet:main`. Deployment of commit `96bb0a943674783e9035449c43150ad1113355bd` was verified successful and the runtime acquired production leadership.

The live scheduler currently composes and runs these jobs:

- fixture discovery;
- model lifecycle/training coverage;
- opportunity evaluation and pick registration;
- Daily Bulletin generation;
- registered-pick odds monitoring and closing finalization;
- result acquisition and settlement processing.

Production runtime logs have verified the complete path through opportunity evaluation and **durable pick registration**: opportunity cycles have emitted `registered_picks > 0`. The system is therefore no longer only capable of producing picks in tests; it has registered picks autonomously in the live Railway environment.

## Read-only dashboard

The V1 dashboard is available at `/` and `/dashboard`. It renders complete pick history,
bankroll/accounting metrics, odds checkpoints, settlement and CLV facts, worker heartbeats,
stale warnings, and provider-budget usage directly from PostgreSQL. It contains no write
route, provider call, betting action, or worker-loop dependency.

Run it as an independent service:

```text
python -m h2h.dashboard_entrypoint
```

For Railway, create a second service from the same repository and set its config file to
`railway.dashboard.json`. Keep the existing worker service on `railway.json`. The dashboard
service needs these variables:

```text
DATABASE_URL
QUANTBET_BANKROLL_ACCOUNT_ID
QUANTBET_INITIAL_BANKROLL_MINOR=3000000
QUANTBET_DASHBOARD_USER=quantbet
QUANTBET_DASHBOARD_PASSWORD=<strong-random-password>
```

Set `QUANTBET_PROCESS=dashboard` when the platform uses the repository's root
`railway.json` instead of `railway.dashboard.json`; the root entrypoint then dispatches
directly to the dashboard-only process and never composes or starts the worker scheduler.

Budget display uses `QUANTBET_API_DAILY_LIMIT`, `QUANTBET_API_RESERVE`,
`QUANTBET_MODEL_TRAINING_DAILY_REQUEST_LIMIT`, and
`QUANTBET_MODEL_TRAINING_OPERATIONAL_RESERVE`, with the same defaults as the worker.
`LOG_LEVEL` and `PORT` are optional. Railway supplies `PORT` automatically. Do not commit
the password; configure it as a Railway variable. If the password is absent, dashboard
routes fail closed with `404`. HTTP Basic authentication remains mandatory when enabled.

The result/settlement/realized-CLV path is implemented, persisted and scheduled in production. This repository does **not** claim that a representative sample of real picks has already completed settlement or that profitability has been established.

## Implemented and production-wired

- Dixon–Coles quant/domain foundation and golden-master regression protection;
- canonical fixture identity with authoritative API-Football provider references and ordered home/away team IDs;
- API-Football fixture discovery and durable fixture observations;
- API-Football odds identity validation, canonical normalization and immutable quote-history ingestion;
- PostgreSQL quote series/snapshots and restart-safe runtime repositories;
- API budget accounting, retry/rate-limit handling and stale-quote retry scheduling;
- trusted FT-only historical result acquisition for model training provenance;
- model-version persistence, active-model loading and scheduled model-lifecycle training/activation;
- fixture-bound production prediction and canonical market/selection probability mapping;
- de-vig/value evaluation and eligibility/freshness/quality policy boundaries;
- final quote verification before registration;
- risk/stake policy, bankroll reservation and open-exposure controls;
- durable decision and immutable registered-pick persistence with duplicate protection;
- Daily Bulletin durable snapshot generation;
- pick-specific odds monitoring, current-price refresh and immutable closing finalization;
- result acquisition, settlement accounting, bankroll ledger integration and realized-CLV persistence path;
- production orchestrator, leader election, readiness/liveness and worker operational status;
- authenticated read-only `/dashboard` and `/api/picks` production read surfaces.

## Current operational limitations

The system is in a **live production-pilot / evidence-collection phase**, not a proven profitable system.

Known limits include:

- some competition/season scopes still fail model training with insufficient historical data and therefore do not have uniform model coverage;
- provider odds can arrive stale, causing bounded retries, final-quote rechecks and missed/blocked opportunities;
- the dashboard remains intentionally read-only and refresh-based; interactive filtering and real-time push updates are outside V1 scope;
- production sample size is still insufficient to make claims about sustained ROI, calibration quality or economic edge.

The correct next validation target is therefore not “can the system make a pick?” — that path is live — but whether the registered production sample demonstrates robust out-of-sample CLV, calibration and realized performance.

## Key documentation

- `docs/PROGRESS.md` — implementation and runtime status.
- `docs/DASHBOARD_SPEC.md` — authoritative Dashboard V1 functional scope.
- `docs/DASHBOARD_DESIGN.md` — approved dashboard visual direction.
- `docs/PICK_REGISTRATION.md` — registration boundary.
- `docs/PICK_MONITORING_ODDS_LIFECYCLE.md` — pick-specific odds lifecycle.
- `docs/RESULTS_SETTLEMENT_PERFORMANCE.md` — result, settlement, bankroll and CLV path.
- `docs/quant-golden-master.md` — locked quant regression baseline.
