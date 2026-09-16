# API-Football HTTP client

`ApiFootballClient` is a thin provider boundary around the provider-neutral
`JsonTransport` protocol.

## Design

- HTTP execution is injected through `JsonTransport`.
- API credentials are supplied at construction time and are never persisted by
  the client.
- The client validates the fixture identifier, API key and timeout.
- Tests use a mock transport; no real API-Football request is made in CI.

The client exposes `fetch_odds(fixture_id=...)`, discovery-oriented
`fetch_fixtures(...)`, and the bounded historical call
`fetch_completed_fixtures(league_id, season, start_at, end_at)`. The historical
call sends the UTC covering calendar dates with `status=FT` and `timezone=UTC`;
strict envelope, record, score and logical-window validation remains the
responsibility of the historical acquisition boundary.

`ApiFootballClient` remains transport- and endpoint-injectable by design. An
instance created directly or by the general client builder does not carry
training-provenance authority and cannot be passed to the trusted historical
acquisition service. Provider-proven training acquisition is constructed only
through `build_trusted_api_football_historical_results(settings)`, which fixes
the canonical endpoint and production HTTP transport internally.

`fixture_id` at this transport boundary is always the positive numeric
API-Football provider ID. `ApiFootballOddsService` derives it from the explicit
provider fixture reference while retaining the resolved opaque canonical ID.
The ingestion boundary validates every response record's `fixture.id` against
the requested provider ID before filtering or flattening any quote branches.
The adapter repeats that check for flattened payloads; accepted quotes receive
the carried canonical ID rather than a raw stringified transport ID.
