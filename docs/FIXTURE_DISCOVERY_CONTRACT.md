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

## API-Football production acquisition

Production discovery maps the UTC calendar dates intersecting the requested timestamp window to global `fixtures?date=YYYY-MM-DD` requests. It does not send league, season or fixture-ID allowlists. Provider results are filtered back to the exact inclusive timestamp window before Phase I classification.

Date shards inside the next 72 hours refresh at most every six hours; later shards refresh at most every 24 hours. Cached shard contents are filtered against the current exact timestamp window on every scheduler wakeup, so most wakeups make no fixture request without losing fixtures as the window rolls. The refresh state is in-process: a restart repopulates the configured horizon once. If any required shard fails, the discovery call fails without returning a partial horizon; successful shards from that incomplete attempt are retained in memory while the failed shard observes a one-hour retry delay.

Acquisition fetches at most two due date shards per scheduler unit, and durable ingestion persists at most ten eligible fixtures per unit. Pending in-memory acquisition and persistence batches resume on subsequent scheduler ticks before the normal 15-minute discovery interval resumes. This keeps opportunity, monitoring and result jobs schedulable during a cold-start horizon load; a process restart rebuilds the in-memory progress from the provider date cache workflow.

## Deliberate scope

Competition filtering, fixture persistence, cross-provider matching, prediction and bulletin orchestration remain separate concerns. Discovery establishes only the provider-qualified fixture reference and its canonical allocation; it does not infer equivalence from names, team IDs, kickoff times or numeric equality.
