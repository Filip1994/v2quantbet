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

## Validacija i hardening

Adapter odbacuje payload-e koji nemaju obavezne sekcije ili validne vrednosti za:

- fixture identifikator;
- home i away timove, uključujući njihove pozitivne identifikatore i nazive;
- league identifikator, naziv, zemlju, tip i sezonu;
- kickoff datum;
- fixture status.

Identifikatori moraju biti pozitivni celi brojevi. Tekstualna polja moraju biti neprazni stringovi, a numeričke vrednosti moraju imati očekivani tip. Datumi se očekuju u ISO formatu; UTC oznaka `Z` se normalizuje u `+00:00` pre parsiranja. Nevalidan tip ili vrednost izaziva eksplicitnu grešku umesto tihe normalizacije.

Validacija se izvršava pre kreiranja canonical objekta, čime se sprečava da provider-specific neispravni podaci uđu u domain sloj.

## Testovi

Testovi pokrivaju:

- uspešno mapiranje validnog API-Football fixture payload-a;
- nedostajuće obavezne sekcije i polja;
- nevalidne ili nepozitivne identifikatore;
- prazne nazive timova i takmičenja;
- nevalidne tipove polja;
- ISO datume i UTC `Z` normalizaciju;
- nevalidne datume i statusne vrednosti.

## Ograničenja

Adapter trenutno prevodi jedan fixture objekat. Traversal kompletnog API response-a, pagination i provider HTTP pozivi ostaju izvan ovog adaptera.
