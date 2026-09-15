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

The repository uses PostgreSQL `ON CONFLICT (series_id, observed_at, source) DO NOTHING`, followed by verification of the stored observation.

## 3. Transaction and concurrency boundary

`append_snapshots()` performs the batch operation inside one database connection context. The database unique constraint is the authoritative protection against concurrent semantic replays. Application-level checks are used to convert conflicting existing payloads into the domain-level `QuoteHistoryConflictError`.

The `snapshot_id` primary-key identity is also checked explicitly before insertion so that a reused identifier cannot silently refer to a different observation.

## 4. Provider contract

This identity is valid only when `observed_at` has stable provider semantics and sufficient precision. Provider adapters must normalize timestamps, odds and source identifiers before constructing domain snapshots.

If a provider exposes only request-time metadata rather than a stable observation timestamp, the adapter must not claim stronger replay guarantees than the provider data supports.

## 5. Migration and operational status

The following database changes have been applied to the Railway PostgreSQL database:

- removed the former uniqueness rule containing `captured_at`;
- added the unique constraint on `(series_id, observed_at, source)`;
- added the supporting observation index;
- recorded `002_quote_snapshot_observation_identity.sql` in `schema_migrations`.

The migration was executed manually through the Railway PostgreSQL console and verified by querying `schema_migrations`.

## 6. Remaining verification

The repository implementation has been updated to guard primary-key conflicts explicitly. Local `pytest` and Ruff results must be reported from the current commit before this iteration is considered fully CI-verified. Real PostgreSQL sequential and concurrent integration tests remain a separate verification task if the test environment is made available.
