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

### API-Football identity boundary

For API-Football, four identity roles remain distinct:

- canonical fixture identity: opaque `api-football:<provider_fixture_id>` used by `CanonicalQuote` and history;
- provider lookup identity: the pair `("api-football", "<provider_fixture_id>")`;
- transport identity: the positive numeric ID sent as `fixture=<id>`;
- provider team identity: ordered home/away IDs qualified by the `api-football` namespace.

Discovery allocates the canonical fixture ID through the shared provider-reference boundary. Odds collection carries that resolved identity while converting only the provider lookup component to the numeric transport ID. Before any bookmaker, bet or value filtering or quote flattening, the ingestion boundary verifies that every response record's fixture ID equals the requested provider fixture ID. The odds adapter repeats the check for each flattened payload, then assigns the already-resolved canonical identity to every quote. Neither layer may stringify the response ID into an independent raw quote identity.

Canonical IDs are compared as opaque strings. Numeric equality, names, teams or kickoff timestamps do not establish fixture equivalence across provider namespaces.

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

The domain layer validates quote structure and consistency. History persistence uses the existing quote-series and observation-identity contracts; canonical fixture identity is an input to those unchanged algorithms.

## Incomplete or contradictory data

Reject payloads that have:

- missing required identity or timestamp data;
- unsupported market or selection values;
- non-positive or non-finite odds;
- inconsistent fixture, bookmaker, market, or observation context within one snapshot;
- duplicate selections where the canonical market requires one quote per selection.

No adapter may silently invent defaults for identity, timestamps, selections, or odds.

## Implementation boundary

Provider adapters may parse API-Football payloads, but they output only the canonical provider-neutral contract. Quant/domain code does not depend on API-Football response structures.
