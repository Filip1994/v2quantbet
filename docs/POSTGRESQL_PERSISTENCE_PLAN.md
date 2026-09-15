# Railway PostgreSQL persistence plan

## Status

**Implementation foundation complete; production hardening and final migration remain separate work.**

Railway PostgreSQL is the target production database for QuantBet. The repository now contains:

- PostgreSQL schema migration for immutable quote history;
- `DATABASE_URL` configuration boundary;
- PostgreSQL application composition and explicit migration hook;
- `PostgreSQLQuoteHistoryRepository` for history-aware quote series and snapshots;
- idempotent inserts using PostgreSQL conflict handling;
- conflict detection for mismatched series or snapshot content;
- isolated unit tests and a real-PostgreSQL integration-test scaffold.

The real-PostgreSQL integration tests require `QUANTBET_TEST_DATABASE_URL` and have not been treated as passed unless executed against an actual PostgreSQL instance.

## Target architecture

```text
Quote history contract
├── InMemoryQuoteHistoryRepository       # tests and local development
└── PostgreSQLQuoteHistoryRepository     # Railway production
```

The provider-neutral quote-history contract remains the boundary. Domain models, quote normalization, ingestion, deduplication and conflict semantics must not depend on PostgreSQL-specific types or APIs.

SQLite is treated as an existing transitional adapter. It must not be deleted until all active consumers have migrated and the PostgreSQL path has passed the required verification.

## Target configuration

- Production connection input: `DATABASE_URL`.
- Credentials and connection details are supplied through Railway Variables/Secrets.
- No database credentials are committed to the repository.
- Local and CI unit tests must not require a live Railway database by default.
- Integration tests may use `QUANTBET_TEST_DATABASE_URL` against an isolated PostgreSQL database.

## Implemented sequence

1. Reviewed and preserved the provider-neutral history contract.
2. Defined the PostgreSQL schema for canonical quote observations.
3. Added migration files under `migrations/`.
4. Added the PostgreSQL connection/configuration boundary using `DATABASE_URL`.
5. Implemented `PostgreSQLQuoteHistoryRepository`.
6. Added protection for:
   - idempotent identical series writes;
   - natural-key series conflicts;
   - idempotent identical snapshot writes;
   - conflicting snapshot IDs;
   - unknown series IDs;
   - atomic batch behavior through one database transaction.
7. Added isolated repository tests and a real-PostgreSQL integration-test scaffold.
8. Added PostgreSQL application composition and an explicit migration lifecycle hook.
9. Updated configuration and storage architecture documentation.

## Restart and concurrency hardening decision

The natural identity of a quote series is:

```text
(fixture_id, bookmaker_id, market, selection)
```

A caller must not assume that its generated `series_id` remains authoritative after a process restart or concurrent creation by another worker. The PostgreSQL adapter must therefore resolve the natural identity before treating a series as newly created:

1. Look up the series by the natural unique key.
2. If found, validate its immutable definition and reuse the persisted `series_id`.
3. If absent, attempt an insert with the caller's proposed `series_id`.
4. On any concurrent unique-key race, resolve the row again by the natural key.
5. Reject only genuine immutable-definition conflicts; never create a second series for the same natural identity.

This is a required hardening rule for the next implementation step. It must be exposed through the provider-neutral repository contract rather than hidden in PostgreSQL-specific application code. Until that contract change is implemented and verified, `ensure_series()` remains a write/validation operation and callers must not infer restart-safe ID resolution from it.

## Remaining work

- Implement and test restart-safe natural-key series resolution.
- Execute the integration suite against a real PostgreSQL instance.
- Confirm the exact migration/bootstrap procedure in the deployed Railway environment.
- Finish production runtime wiring for all required history-aware use cases.
- Remove SQLite only after active consumers, tests and CI have been migrated and verified.
- Add persistence models for picks, bankroll ledger and dashboard read models in separate, explicitly scoped iterations.

## Explicitly out of scope for this step

- PickRegistration persistence;
- ValuePick persistence;
- CLV storage;
- Research data model;
- deletion of existing SQLite code;
- changes to quant mathematics or domain contracts.

## Acceptance criteria

The PostgreSQL persistence foundation is considered complete when:

- the adapter satisfies the history repository contract;
- schema creation is reproducible through migrations;
- conflict and idempotency semantics are implemented;
- configuration is environment-based;
- isolated tests exist;
- real-PostgreSQL integration verification is explicitly tracked;
- documentation reflects the actual implementation state;
- SQLite removal is performed as a separate, explicitly verified step.
