# Fixture Discovery Contract

## Purpose

The canonical `Fixture` model represents a scheduled football match independently of API-Football or any other provider. This prevents provider-specific payloads from leaking into application and domain logic.

## Canonical fixture

A fixture contains the stable internal identifier, teams, competition metadata, kickoff timestamp, status, provider name, and optional provider fixture reference.

The model is immutable and validates required identifiers, names, competition ID, provider, and kickoff type at construction time.

## Discovery port

`FixtureDiscovery` defines the provider-neutral application boundary:

```python
discover(start_at: datetime, end_at: datetime) -> Sequence[Fixture]
```

An adapter is responsible for translating this request to a provider API and returning canonical `Fixture` objects. The contract does not prescribe HTTP, authentication, pagination, or provider payload structure.

## Deliberate scope

This change introduces the domain object and port only. Competition filtering, provider mapping, persistence, and bulletin orchestration remain separate steps and will be implemented with their own tests and CI verification.
