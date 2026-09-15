# QuantBet — Quote Ingestion Idempotency Decision

**Date:** 2026-09-15  
**Status:** Implemented for the PostgreSQL quote-history persistence boundary

## 1. Canonical observation identity

For a normalized pre-match quote observation, the database identity is:

```text
(series_id, observed_at, source)
```

Where:

- `series_id` identifies the fixture, bookmaker, market and selection;
- `observed_at` is the provider observation timestamp after timezone normalization;
- `source` is a stable source identifier;
- `odd` is the immutable numeric payload of that observation;
- `captured_at` is ingestion metadata and does not define observation identity.

The PostgreSQL constraint is implemented by migration
`002_quote_snapshot_observation_identity.sql`.

## 2. Required behavior

| Situation | Required behavior |
|---|---|
| Same semantic observation replayed with the same payload | Idempotent no-op |
| Same semantic identity with a different odd | `QuoteHistoryConflictError` |
| Same semantic identity with different capture time but same payload | Idempotent no-op at the semantic identity boundary |
| Different observation timestamp | Append a new historical observation |
| Same `snapshot_id` with a different payload | `QuoteHistoryConflictError` |
| Unknown `series_id` | `QuoteHistoryConflictError` |

Semantic replay preserves the first stored snapshot, including its `snapshot_id`
and `captured_at`. A different proposed snapshot ID does not create an alias or
another row. A capture-time-only change is metadata, not incompatible observation
payload, even when the same snapshot ID is supplied. Reusing a stored snapshot ID
with a different series, observation timestamp, source or odd remains a conflict.

The repository uses PostgreSQL `ON CONFLICT (series_id, observed_at, source) DO NOTHING`, followed by verification of the stored observation.

## 3. Transaction and concurrency boundary

`append_snapshots()` performs the batch operation inside one database connection context. The database unique constraint is the authoritative protection against concurrent semantic replays. Application-level checks are used to convert conflicting existing payloads into the domain-level `QuoteHistoryConflictError`.

The `snapshot_id` primary-key identity is also checked explicitly before insertion so that a reused identifier cannot silently refer to a different observation.

## 4. Provider contract

This identity is valid only when `observed_at` has stable provider semantics and sufficient precision. Provider adapters must normalize timestamps, odds and source identifiers before constructing domain snapshots.

If a provider exposes only request-time metadata rather than a stable observation timestamp, the adapter must not claim stronger replay guarantees than the provider data supports.

## 5. Migration and operational status

The earlier operational record reports the following changes to Railway PostgreSQL
(not independently re-observed during the remediation below):

- removed the former uniqueness rule containing `captured_at`;
- added the unique constraint on `(series_id, observed_at, source)`;
- added the supporting observation index;
- recorded `002_quote_snapshot_observation_identity.sql` in `schema_migrations`.

That record states that the migration was executed manually through the Railway
PostgreSQL console and checked through `schema_migrations`. This remediation makes
no live Railway changes or new live-verification claim.

## 6. Remaining verification

The 2026-09-15 regression triage confirmed fully-migrated PostgreSQL runtime
incompatibility (classification F): the repository had regressed to a four-column
conflict target absent after migration 002. Commit `cea53a990c602c9d53d7a62ec64d8c62c92ef359`
restores the three-column insert/lookup contract and aligns in-memory semantics.
Neither migration is changed. Integration bootstrap now calls `apply_migrations()`
and asserts all migration versions plus the final three-column unique constraint.

Final local targeted tests: 51 passed. Ruff passed. Local real PostgreSQL was not
available; integration coverage expanded from 6 to 15 cases. The one full local
run returned 356 passed, 1 failed, 15 skipped. Its stale ingestion expectation was
corrected and verified in the final targeted run; the full local suite was not
repeated. See `CODEX_VERIFICATION_REPORT.md` for CI status. Unit doubles do not prove
SQL constraint compatibility; concurrency behavior needs separate real-DB coverage.

Real PostgreSQL verification subsequently passed in existing PR CI:
[run 35000997862](https://github.com/Filip1994/v2quantbet/actions/runs/35000997862),
implementation head `cea53a990c602c9d53d7a62ec64d8c62c92ef359`, PostgreSQL 16.15.
All 15 integration cases passed; full CI result: 372 passed, 0 failed/skipped/errors;
Ruff passed. This is CI database verification, not a live Railway observation.
