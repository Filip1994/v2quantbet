# Odds ingestion contract

## Scope

This document defines provider-neutral ingestion semantics. Provider-specific payload shapes and field names remain inside provider adapters.

## Identity

A canonical quote is identified by:

`(fixture_id, bookmaker_id, market, selection)`

The identity must be stable across repeated ingestion runs. A provider name, display label, or odd value is not part of the quote identity.

- `fixture_id` identifies the sporting fixture in the canonical system.
- `bookmaker_id` identifies the bookmaker using a stable provider-independent mapping.
- `market` and `selection` use the canonical enums from the domain layer.
- `bookmaker_name` is descriptive metadata and must not be used as the primary key.

If a provider cannot resolve a stable fixture or bookmaker identity, the payload must be rejected rather than silently assigned a guessed identity.

## Market and selection mapping

Adapters must translate provider-specific market labels into canonical `Market` and `Selection` values before creating `CanonicalQuote` objects. Unknown or unsupported mappings are rejected explicitly.

A market snapshot is valid only when it contains the complete selection set required by the canonical market definition. Missing selections are invalid; they must not be filled with synthetic odds.

## Time semantics

`observed_at` is the provider-observation time of the quoted odd. It must be timezone-aware and represents when the provider observed or published the quote, not when the application happened to process it.

An ingestion implementation may additionally record an application processing time (`ingested_at`) in its persistence/operational layer. That field is not interchangeable with `observed_at` and does not belong in the canonical quote identity.

If the provider timestamp is absent, malformed, or timezone-naive, the adapter must reject the payload unless a separately specified, auditable provider rule supplies a reliable timestamp.

## Duplicate and idempotency rules

Repeated delivery of the same canonical identity is expected in ingestion systems. The ingestion boundary must be idempotent:

- identical identity and identical quote data may be safely reprocessed;
- conflicting quote data for the same identity must not be silently overwritten;
- conflict handling must be explicit (for example, versioning by `observed_at`, quarantine, or a domain-specific conflict error).

The current domain layer validates quote structure and consistency; persistence-level deduplication and conflict resolution remain future work.

## Incomplete or contradictory data

Reject payloads that have:

- missing required identity or timestamp data;
- unsupported market or selection values;
- non-positive or non-finite odds;
- inconsistent fixture, bookmaker, market, or observation context within one snapshot;
- duplicate selections where the canonical market requires one quote per selection.

No adapter may silently invent defaults for identity, timestamps, selections, or odds.

## Implementation boundary

The next concrete adapter may parse API-Football payloads, but it must output only the canonical provider-neutral contract. Quant/domain code must not depend on API-Football response structures.
