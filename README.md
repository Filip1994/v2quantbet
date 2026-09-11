# H2H V2

Clean rebuild of the football value-betting system.

The existing `h2h` repository is legacy/reference only. Do not copy its
runtime infrastructure into this repository.

## Principles

- Quantitative model mathematics is preserved and regression-tested before infrastructure changes.
- Odds are acquired through a canonical quote interface.
- PostgreSQL is the planned canonical production state store.
- Railway is the planned runtime/deployment platform.
- No production implementation is accepted without passing tests.
- Small, isolated tasks only; unrelated cleanup is forbidden.

## Current status

A1 — repository skeleton.

Next: A2 — development tooling and minimal test setup.
