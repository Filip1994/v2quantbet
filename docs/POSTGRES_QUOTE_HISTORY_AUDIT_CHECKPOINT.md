# QuantBet — PostgreSQL Quote-History Audit Checkpoint

**Date:** 2026-09-15
**Status:** Historical checkpoint with observation-identity remediation follow-up below

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

## Observation-identity remediation — 2026-09-15

The prior verification paragraph describes the earlier API-authored checkpoint,
not the latest local execution. Subsequent triage confirmed classification F:
fully migrated PostgreSQL had no unique arbiter for the regressed four-column
snapshot INSERT target. The canonical key is `(series_id, observed_at, source)`;
`captured_at` is provenance only. PostgreSQL and in-memory replay now preserve the
original row for the same observation/odd, including when capture time or the
proposed snapshot ID changes. Changed odd or incompatible reused ID still conflicts.

Integration tests use the real migration runner, including 002, and check migration
records and the final unique constraint. Local final targeted verification: 51
passed; Ruff passed. The one local full run was 356 passed, 1 failed, 15 skipped;
the stale ingestion assertion was then fixed and passed targeted verification.
No second local full run or PostgreSQL provisioning was performed. Real PostgreSQL
CI results are recorded in `CODEX_VERIFICATION_REPORT.md`; fake tests alone are not
database compatibility evidence. The existing concurrency question above is not
resolved by these sequential regression tests.

Existing PR CI has now executed the real database tests successfully:
[run 35000997862](https://github.com/Filip1994/v2quantbet/actions/runs/35000997862),
head `cea53a990c602c9d53d7a62ec64d8c62c92ef359`, PostgreSQL 16.15.
Result: 15 integration cases passed; 372 total passed, zero failed/skipped/errors;
Ruff passed. The earlier real-DB execution blocker is resolved for these tests,
not for concurrent-writer scenarios or live Railway deployment.
