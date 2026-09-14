# API-Football Fixture Adapter

## Svrha

`ApiFootballFixtureAdapter` prevodi jedan API-Football fixture payload u canonical, immutable `h2h.domain.fixture.Fixture` objekat.

## Mapiranje

- `fixture.id` → `provider_fixture_id` i canonical ID `api-football:<id>`
- `teams.home.name` → `home_team`
- `teams.away.name` → `away_team`
- `league.id` → `competition_id`
- `league.name` → `competition_name`
- `league.country` → `country`
- `league.type` → `competition_type`
- `league.season` → `season`
- `fixture.date` → timezone-aware `kickoff_at`
- `fixture.status.short` → `status`

## Arhitektonska pravila

Adapter je provider-specific sloj. Canonical domain model ne zna za API-Football strukturu, ključeve ili response envelope.

Adapter ne primenjuje competition-scope politiku; to ostaje odgovornost `ScopedFixtureDiscovery` use-case-a.

## Validacija

Odbacuju se payload-i bez obaveznih sekcija, identifikatora, imena timova, takmičenja ili kickoff datuma. Datumi se očekuju u ISO formatu; `Z` se normalizuje u `+00:00`.

## Ograničenja

Adapter trenutno prevodi jedan fixture objekat. Traversal kompletnog API response-a, pagination i provider HTTP pozivi ostaju izvan ovog adaptera.
