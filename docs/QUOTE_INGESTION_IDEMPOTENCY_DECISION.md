# QuantBet — Quote Ingestion Idempotency Decision

**Date:** 2026-09-15  
**Status:** Proposed implementation decision — not yet implemented

## 1. Finding

QuantBet currently has database-level protection against duplicate physical rows:

- `quote_series` has a unique natural identity:
  `(fixture_id, bookmaker_id, market, selection)`;
- `quote_snapshots.snapshot_id` is the primary key;
- `quote_snapshots` also has a uniqueness constraint on:
  `(series_id, observed_at, captured_at, source)`.

This protects storage integrity, but the `captured_at` component means that the same provider observation can potentially be stored again if it is persisted at a later time with a different capture timestamp and a new `snapshot_id`.

Therefore, the current schema is **not sufficient to prove semantic API-replay idempotency**.

## 2. Recommended semantic identity

For a normalized pre-match quote observation, the recommended deduplication identity is:

```text
(series_id, observed_at, canonical_odd, canonical_source)
```

Where:

- `series_id` identifies fixture, bookmaker, market and selection;
- `observed_at` is the provider observation timestamp after timezone normalization;
- `canonical_odd` is the normalized numeric quote value;
- `canonical_source` is a stable source identifier, not a request-specific trace ID;
- `captured_at` is operational metadata and must not determine semantic identity.

A deterministic fingerprint may be derived from these canonical fields if the implementation needs a compact idempotency key.

## 3. Required behavior

The ingestion layer must distinguish:

| Situation | Required behavior |
|---|---|
| Exact replay of the same normalized observation | Idempotent no-op |
| Same series and timestamp, changed odd | Explicit conflict or a new observation only if provider semantics prove the timestamp is not an immutable observation time |
| Different observation timestamp | Append a new historical observation |
| Same quote captured later | Do not create a second semantic observation |
| Different stable source | Treat according to an explicit source policy; never silently merge unrelated providers |
| Invalid odd or timestamp | Reject with a machine-readable reason |
| Post-kickoff observation | Reject or exclude from pre-match history |

## 4. Important provider constraint

The proposed key is valid only if `observed_at` has stable provider semantics. If the provider supplies only a request-time timestamp or a timestamp with insufficient precision, the ingestion adapter must first establish a stronger observation identity or explicitly document that replay deduplication cannot be guaranteed from provider data alone.

Provider payloads must be normalized before reaching persistence. Raw provider fields must not be used as an accidental substitute for a canonical domain contract.

## 5. Implementation implications

Before changing the schema or repository, the following must be completed:

1. Confirm the semantics and precision of the provider observation timestamp.
2. Define canonical odd normalization and decimal precision.
3. Define the stable source vocabulary.
4. Decide whether conflicting values for the same semantic key are rejected, versioned, or treated as provider correction events.
5. Replace the current `captured_at`-dependent uniqueness rule with an explicitly approved semantic uniqueness strategy.
6. Add real PostgreSQL tests for sequential replay and concurrent replay.
7. Add ingestion tests proving that the same API response cannot create multiple semantic observations.

## 6. Current status

No schema or runtime ingestion change is made by this document. The existing persistence protections remain in place, but API-level semantic idempotency is not considered complete until the above contract is approved and implemented.
