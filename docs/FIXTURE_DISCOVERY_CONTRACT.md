# Fixture Discovery Contract

## Purpose

The canonical `Fixture` model represents a scheduled football match independently of API-Football or any other provider. This prevents provider-specific payloads from leaking into application and domain logic.

## Canonical fixture

A fixture contains the stable internal identifier, teams, competition metadata, kickoff timestamp, status, provider name, and optional provider fixture reference.

The model is immutable and validates required identifiers, names, competition ID, provider, and kickoff type at construction time.

For API-Football, the central provider-reference boundary allocates canonical `fixture_id` as `api-football:<provider_fixture_id>`. The provider reference remains the separate pair `("api-football", "<provider_fixture_id>")`; its positive numeric component is used only for API transport. Discovered fixtures also retain ordered, provider-qualified home and away team IDs. Those team IDs are not global canonical team identities.

## Discovery port

`FixtureDiscovery` defines the provider-neutral application boundary:

```python
discover(start_at: datetime, end_at: datetime) -> Sequence[Fixture]
```

An adapter is responsible for translating this request to a provider API and returning canonical `Fixture` objects. The contract does not prescribe HTTP, authentication, pagination, or provider payload structure.

## Deliberate scope

Competition filtering, fixture persistence, cross-provider matching, prediction and bulletin orchestration remain separate concerns. Discovery establishes only the provider-qualified fixture reference and its canonical allocation; it does not infer equivalence from names, team IDs, kickoff times or numeric equality.
