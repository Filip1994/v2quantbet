# API-Football Fixture Adapter

## Svrha

`ApiFootballFixtureAdapter` prevodi jedan API-Football fixture payload u canonical, immutable `h2h.domain.fixture.Fixture` objekat.

## Mapiranje

- `fixture.id` → `provider_fixture_id` i canonical ID `api-football:<id>`
- `teams.home.name` → `home_team`
- `teams.away.name` → `away_team`
- `teams.home.id` → `provider_home_team_id`
- `teams.away.id` → `provider_away_team_id`
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

Canonical `fixture_id` i provider lookup identitet imaju odvojene uloge. Za fixture poreklom iz API-Football-a canonical identitet je `api-football:<provider_fixture_id>`, dok `provider_fixture_id` zadržava sirovi provider ID koji polling/transport sloj pretvara u pozitivan ceo broj za API-Football poziv. `CanonicalQuote.fixture_id` sada koristi isti canonical identitet; raw provider ID više nije quote identitet.

`ProviderFixtureReference` predstavlja provider namespace i provider fixture ID kao odvojen immutable par. `ResolvedFixtureIdentity` ga vezuje za canonical `fixture_id`, a centralna API-Football alokacija je jedino mesto koje formira `api-football:<id>`. Discovery i odds ingestion koriste isti resolved identitet; downstream poslovna logika tretira canonical ID kao opaque string i ne parsira ga.

Produkcioni PostgreSQL je pre ovog cutover-a potvrđen kao prazan, pa nema legacy raw quote ID-jeva ili istorijskih serija za aliasiranje. Quote adapter više ne konstruiše raw `CanonicalQuote.fixture_id`. Odgovor odds API-ja mora sadržati isti provider fixture ID koji je transport zahtevao ili se odbacuje.

`provider_home_team_id` i `provider_away_team_id` čuvaju originalni redosled iz provider payload-a i eksplicitno su kvalifikovani vrednošću `Fixture.provider`. Nisu globalni, provider-neutralni team identiteti. Mogu se proslediti Dixon–Coles modelu samo kada je eksplicitno utvrđeno da fitted training skup koristi isti provider namespace; adapter sam ne uspostavlja tu vezu.

Production prediction boundary sada iz `Fixture` objekta interno gradi immutable target, izlaže ga kroz read-only `PredictionTarget` interfejs, proverava canonical/provider fixture konzistentnost, odbija jednake home/away team ID vrednosti i čuva isti home/away redosled. Read-only `FixturePrediction` rezultat nema podržan javni konstruktor i identity-safe valuation prihvata samo konkretan rezultat koji je proizveo `DixonColesFixturePredictor`. Predictor odbija model čiji `team_id_namespace` nije `api-football` pre numeričkog prediction poziva. Namespace na modelu je eksplicitna tvrdnja fit caller-a, ne dokaz porekla trening podataka; production acquisition istorijskih API-Football rezultata još nije implementiran.

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
- očuvanje provider home/away team ID-jeva i njihovog redosleda;
- očuvanje numeričkog API-Football fixture ID-ja na polling/transport granici;
- nedostajuće obavezne sekcije i polja;
- nevalidne ili nepozitivne identifikatore;
- prazne nazive timova i takmičenja;
- nevalidne tipove polja;
- ISO datume i UTC `Z` normalizaciju;
- nevalidne datume i statusne vrednosti.

## Ograničenja

Adapter trenutno prevodi jedan fixture objekat. Traversal kompletnog API response-a, pagination i provider HTTP pozivi ostaju izvan ovog adaptera.
