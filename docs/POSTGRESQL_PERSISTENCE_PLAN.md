# Railway PostgreSQL persistence plan

## Status

**Architecture decision confirmed.** Railway PostgreSQL is the target production database for QuantBet.

This document defines the target and migration sequence only. It does not introduce the PostgreSQL implementation yet.

## Target architecture

```text
QuoteRepository
├── InMemoryQuoteRepository    # tests and local development
└── PostgreSQLQuoteRepository  # Railway production
```

The provider-neutral `QuoteRepository` contract remains the boundary. Domain models, quote normalization, ingestion, deduplication and conflict semantics must not depend on PostgreSQL-specific types or APIs.

SQLite is treated as an existing transitional adapter. It must not be deleted until the PostgreSQL adapter and its tests provide an equivalent supported path.

## Target configuration

- Production connection input: `DATABASE_URL`.
- Credentials and connection details are supplied through Railway Variables/Secrets.
- No database credentials are committed to the repository.
- Local and CI tests must not require a live Railway database by default.

## Implementation sequence

1. Review and freeze the current `QuoteRepository` contract and its behavioral guarantees.
2. Define the PostgreSQL schema for canonical quote observations.
3. Add migration files under `migrations/`.
4. Add a PostgreSQL connection/configuration boundary using `DATABASE_URL`.
5. Implement `PostgreSQLQuoteRepository` behind the existing contract.
6. Preserve and test:
   - idempotent identical writes;
   - conflict detection for the same canonical identity;
   - atomic batch behavior;
   - `all()` retrieval;
   - `for_fixture()` retrieval.
7. Add isolated repository tests and, where available, a PostgreSQL integration test job/service.
8. Add production application composition for the PostgreSQL repository.
9. Update configuration and architecture documentation.
10. Remove SQLite only after PostgreSQL implementation, tests and CI verification are complete.

## Explicitly out of scope for this step

- PickRegistration persistence;
- ValuePick persistence;
- CLV storage;
- Research data model;
- Railway deployment changes;
- deletion of existing SQLite code;
- changes to quant mathematics or domain contracts.

## Acceptance criteria

The PostgreSQL persistence step is complete only when:

- the adapter satisfies the existing repository contract;
- schema creation is reproducible through migrations;
- conflict and idempotency semantics are covered by tests;
- configuration is environment-based;
- CI passes;
- documentation and `docs/PROGRESS.md` reflect the actual state;
- SQLite removal is performed as a separate, explicitly verified step.
