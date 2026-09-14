# QuantBet — Data Storage Architecture

## Scope

This document defines where QuantBet data is stored in the Railway deployment, which system is authoritative, and what must never be treated as the source of truth.

## Railway components

The production project consists of three distinct resource types:

1. **QuantBet application service** — executes ingestion, validation, calculations, workers and reporting jobs.
2. **Railway PostgreSQL** — durable structured persistence and the authoritative business-data store.
3. **Railway Durable Barrel** — durable file storage for explicitly approved artifacts, caches and large local files.

RAM/Memory and CPU are execution resources, not storage systems.

## Source of truth

**PostgreSQL is the source of truth for all structured QuantBet business data.**

The application service is compute-only: it may process data, but its local filesystem, RAM, logs and generated files are not authoritative records.

The Durable Barrel is not a second database and must not become an untracked source of truth.

## Storage ownership

| Data | Authoritative location | Notes |
|---|---|---|
| Raw provider events and normalized fixtures | PostgreSQL | Keep provider identifiers and ingestion timestamps. |
| Historical odds/quotes | PostgreSQL | The quote-history tables are authoritative. |
| Model inputs and calculated signals | PostgreSQL | Store reproducible inputs, model/version metadata and timestamps where required. |
| Value-betting candidates | PostgreSQL | Persist the decision inputs and calculation version for auditability. |
| Daily bulletin records | PostgreSQL | Generated files may be exported separately, but the underlying records remain in PostgreSQL. |
| Research findings and derived metrics | PostgreSQL | Files are secondary artifacts, not the canonical dataset. |
| Job runs, ingestion status and errors requiring audit | PostgreSQL | Operational logs may supplement this, but audited state belongs in the database. |
| Secrets and connection strings | Railway environment variables/secrets | Never store them in PostgreSQL, the repository or the Durable Barrel. |
| Temporary cache | Durable Barrel, if needed | Must be rebuildable and safe to delete. |
| Large model/data artifacts | Durable Barrel, if needed | Must have version, checksum and provenance recorded in PostgreSQL. |
| Generated CSV/JSON/Markdown/PDF exports | Durable Barrel or external artifact storage | Treat as disposable/reproducible unless explicitly versioned. |
| Application logs | Railway logging system | Do not use logs as the business database. |
| Runtime RAM | Application process memory | Ephemeral; never persistent. |

## Durable Barrel rules

The Durable Barrel may be used only when all of the following are true:

- the data is file-shaped or too large/inefficient for PostgreSQL;
- the application can identify its owner and lifecycle;
- the file can be regenerated or is backed up independently;
- its version, checksum or metadata is recorded in PostgreSQL when reproducibility matters;
- deleting the barrel would not silently destroy the canonical business dataset.

Do not store the only copy of quotes, bets, signals, fixtures or audit records on the barrel.

A Durable Barrel is not automatically a PostgreSQL backup. Backup and restore must use the database provider's supported mechanisms and must be tested separately.

## Application deployment rules

- Production configuration must use `DATABASE_URL`.
- The Railway runtime must not select SQLite as a fallback.
- Database migrations must run through an explicit startup/deployment procedure.
- Workers must write durable business state to PostgreSQL.
- Restarts and redeployments must be safe because business data is external to the application container.
- Any barrel-backed cache must tolerate loss, corruption and rebuild.

## SQLite policy

SQLite is not part of the target production architecture. Existing SQLite code may remain temporarily for isolated legacy tests or migration work, but no Railway production path may depend on it.

The removal sequence is:

1. remove active runtime references;
2. migrate or replace affected tests;
3. verify PostgreSQL-only composition and startup;
4. delete obsolete SQLite implementation and configuration;
5. update documentation and CI.

## Non-goals

This document does not claim that backups, disaster recovery, monitoring or production worker startup are already complete. Those are separate implementation and verification tasks.
