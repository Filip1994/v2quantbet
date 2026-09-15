# API-Football HTTP client

`ApiFootballClient` is a thin provider boundary around the provider-neutral
`JsonTransport` protocol.

## Design

- HTTP execution is injected through `JsonTransport`.
- API credentials are supplied at construction time and are never persisted by
  the client.
- The client validates the fixture identifier, API key and timeout.
- Tests use a mock transport; no real API-Football request is made in CI.

The current client exposes `fetch_odds(fixture_id=...)` and returns the decoded
provider JSON object. Mapping that response into canonical quotes remains the
responsibility of the existing ingestion and adapter layers.

`fixture_id` at this transport boundary is always the positive numeric
API-Football provider ID. `ApiFootballOddsService` derives it from the explicit
provider fixture reference while retaining the resolved opaque canonical ID.
The ingestion boundary validates every response record's `fixture.id` against
the requested provider ID before filtering or flattening any quote branches.
The adapter repeats that check for flattened payloads; accepted quotes receive
the carried canonical ID rather than a raw stringified transport ID.
