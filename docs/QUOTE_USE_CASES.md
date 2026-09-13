# Quote application use case

`QuoteIngestionService` is the application boundary between orchestration code and the provider-neutral `QuoteRepository` contract.

## Responsibilities

- accept only canonical `CanonicalQuote` objects;
- delegate writes to the repository;
- expose fixture-scoped reads;
- expose deterministic full reads;
- preserve repository atomicity and conflict semantics.

## Non-responsibilities

The service does not parse provider payloads, perform quant calculations, or know about database technology. Provider adapters belong in the odds ingestion layer; persistence implementations belong behind `QuoteRepository`.
