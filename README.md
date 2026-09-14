# QuantBet

QuantBet is a pre-match football value-betting engine.

## Architecture

- **GitHub** — source code, version control, tests and CI.
- **Railway engine service** — background worker runtime.
- **Railway PostgreSQL** — canonical persistent state store.
- **API/dashboard** — separate future services; not part of the worker runtime yet.

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
- canonical quote validation and provider-neutral normalization;
- immutable quote-series and quote-snapshot domain models;
- in-memory quote-history repository;
- PostgreSQL quote-history adapter;
- PostgreSQL migration runner;
- CI lint and test verification.

In progress:

- production worker entrypoint and application composition;
- PostgreSQL runtime initialization;
- optional live PostgreSQL integration tests;
- Railway deployment configuration.

The project is not yet production-ready as an end-to-end betting engine.
