# Persistence boundary

## Scope

The persistence layer accepts and returns only `CanonicalQuote` domain objects. Provider-specific payloads, adapters and API response shapes must remain outside this boundary.

## Contract

`QuoteRepository` defines three operations:

- `save(quotes)`: persist observations idempotently;
- `all()`: return all stored observations in insertion order;
- `for_fixture(fixture_id)`: return observations for one fixture.

## Conflict policy

- An exact repeated `CanonicalQuote` is ignored.
- Two observations with the same canonical `identity` but different data raise `QuoteConflictError`.
- `save()` is atomic: if any incoming quote conflicts, no incoming quote is stored.

`InMemoryQuoteRepository` is intentionally a test/local implementation. A database-backed implementation can be added later behind the same provider-neutral contract.
