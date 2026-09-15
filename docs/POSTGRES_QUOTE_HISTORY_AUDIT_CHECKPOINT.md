# QuantBet — PostgreSQL Quote-History Audit Checkpoint

**Date:** 2026-09-15
**Status:** Audit checkpoint; runtime verification pending

## Finding

The PostgreSQL quote-history repository exposes `find_series()` for lookup by the natural series identity:

- `fixture_id`
- `bookmaker_id`
- `market`
- `selection`

The repository implementation was reviewed, and the PostgreSQL test double was updated so that `fetchone()` correctly returns the matching row for this lookup.

## Test coverage added

The PostgreSQL persistence test suite now explicitly covers:

- successful natural-identity lookup;
- `None` for a missing natural identity;
- distinction between `OVER` and `UNDER` selections;
- preservation of the existing series, snapshot, idempotency, and conflict tests.

## Verification status

The test file was updated through the GitHub Contents API. `pytest`, Ruff, and a real PostgreSQL integration test were **not run in this environment**. The change must therefore be treated as unverified until local or CI execution confirms it.

## Next audit target

The next persistence audit should verify the real PostgreSQL behavior for the composite natural-identity uniqueness constraint under concurrent `ensure_series()` calls. The test double cannot establish that database-level property.
