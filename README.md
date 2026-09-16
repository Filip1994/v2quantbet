# QuantBet

QuantBet is a pre-match football value-betting engine.

## Architecture

- **GitHub** — source code, version control, tests and CI.
- **Railway engine service** — intended background-worker deployment target; repository code includes the worker entrypoint, but this document does not claim a live deployment.
- **Railway PostgreSQL** — target canonical persistent state store; the repository contains the PostgreSQL quote-history path.
- **API/dashboard** — separate future services; not implemented as an operational read surface yet.

The engine is strictly pre-match. It records quote observations up to kickoff and does not process live/in-play odds.

## Development principles

- Quantitative model mathematics is regression-tested before infrastructure changes.
- Odds are acquired through canonical, provider-neutral interfaces.
- PostgreSQL is the production persistence target.
- No production implementation is accepted without passing tests.
- Changes are implemented in small, verifiable functional increments.
- Secrets belong in the local environment or Railway variables, never in Git.

## Current status

Implemented and tested:

- quant/domain foundation and regression anchors;
- API-Football fixture discovery with canonical `api-football:<id>` identity and ordered provider team IDs;
- API-Football odds identity validation and canonical quote ingestion;
- canonical quote validation and provider-neutral normalization;
- immutable quote-series and quote-snapshot domain models;
- in-memory and PostgreSQL quote-history repositories;
- PostgreSQL migration runner;
- discovery-driven quote polling and the PostgreSQL worker/runtime entrypoint;
- fixture-bound Dixon–Coles prediction targeting and identity-safe value evaluation;
- FT-only API-Football completed-match acquisition with strict score/scope validation,
  conflict-safe deduplication, production-bound transport/endpoint provenance and a
  provenance-derived Dixon–Coles team namespace;
- CI lint and test verification.

Not implemented or not production-wired yet:

- model artifact/version lifecycle and durable prediction/value provenance;
- broader training orchestration and production fixture-to-model execution;
- concrete eligibility, freshness, quality, de-vig, risk and stake policy;
- Daily Bulletin generation and delivery;
- pick-specific monitoring, designated closing capture, settlement and realized CLV;
- operational API/dashboard, observability, deployment and pilot verification.

The project is not yet production-ready as an end-to-end betting engine.
