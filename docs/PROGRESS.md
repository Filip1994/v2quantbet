# QuantBet — Progress

## Trenutno stanje

Quant/domain foundation je izgrađen i testiran: Dixon–Coles baseline, golden-master zaštita, javni quant API, canonical quote modeli, market snapshot validacija i provider-neutral quote normalizacija.

Provider-neutral quote adapter contract, API-Football adapter, ingestion, persistence, configuration, HTTP transport, API-Football client i application service su implementirani kao odvojeni slojevi.

Prvi value-evaluation sloj je implementiran: model-vs-market poređenje računa implied probability, probability gap i expected value uz validaciju model probability granica.

Fixture discovery foundation je uveden kroz canonical `Fixture` model, provider-neutral `FixtureDiscovery` contract, `ScopedFixtureDiscovery` use-case i API-Football fixture adapter sa hardening validacijom.

Dodatno je definisana jasna granica između operativnog Daily Bulletin screeninga i budućeg Research sektora.

## Završeno

- Quant/domain foundation i regresiona zaštita.
- Canonical quote modeli i market snapshot validacija.
- Provider-neutral quote adapter contract.
- API-Football flattening, normalization, deduplication i conflict handling.
- In-memory i SQLite persistence sa idempotentnim upisom i atomskim odbijanjem konflikata.
- Quote ingestion use case i SQLite application composition/lifecycle.
- Environment konfiguracija sa obaveznim `API_FOOTBALL_KEY` i podrazumevanom SQLite putanjom.
- Provider-neutral `JsonTransport` i `UrllibJsonTransport` sa timeout/error mapiranjem.
- `ApiFootballClient` sa pravilnim `/odds?fixture=<id>` zahtevom.
- `ApiFootballOddsService` koji povezuje client sa ingestion i snapshot slojem.
- `RetryingJsonTransport` sa ograničenim brojem pokušaja i eksponencijalnim backoff-om.
- HTTP 429 klasifikacija kroz `TransportRateLimitError` sa očuvanim `Retry-After` intervalom.
- Dnevni `DailyApiBudget` sa operativnom rezervom i `BudgetedJsonTransport` zaštitom.
- Fixture-level in-memory TTL cache za API-Football odgovore, sa eksplicitnim invalidiranjem.
- Definisan Phase I scope takmičenja i pravila za isključivanje afričkih, omladinskih, nižerazrednih engleskih/nemačkih i kup takmičenja.
- Deterministički Phase I competition-scope filter sa stabilnim rejection reason kodovima.
- Deterministička ValuePick evaluacija: implied probability, probability gap i expected value.
- Canonical immutable `Fixture` model.
- Provider-neutral `FixtureDiscovery` contract.
- `ScopedFixtureDiscovery` use-case za primenu Phase I universe politike.
- API-Football fixture adapter za mapiranje provider payload-a u canonical `Fixture`.
- Hardening validacija fixture adaptera i prošireni testovi za nevalidne payload-e, tipove, identifikatore i datume.
- Immutable `PickRegistration` model sa `PickStatus` lifecycle enumeracijom.
- Testovi i dokumentacija za navedene celine.
- Prošireni product goals sa Research sektorom i eksplicitnom granicom prema production screeningu.
- Dodat plan Research sektora u `docs/RESEARCH_SECTOR_PLAN.md`.
- CI potvrđen kao zelen za poslednju implementacionu ispravku: run `34819806932`.
- Uveden detaljni ljudski čitljiv dnevnik manjih iteracija u `docs/ITERATION_LOG.md`.
- Dodat dizajn istorijskih pre-match quote snapshot-a u `docs/HISTORICAL_PREMATCH_QUOTES_DESIGN.md`.

## Arhitektonske odluke

- Railway PostgreSQL je potvrđena ciljna production baza.
- `QuoteRepository` ugovor ostaje provider-neutral i ne menja se zbog izbora baze.
- `InMemoryQuoteRepository` ostaje za testove i lokalni razvoj.
- PostgreSQL adapter će biti uveden kao `PostgreSQLQuoteRepository` iza postojećeg ugovora.
- SQLite ostaje privremeni postojeći adapter dok PostgreSQL implementacija i testovi ne budu završeni.
- SQLite se neće brisati pre uspešne PostgreSQL zamene i CI verifikacije.
- Detaljan plan je u `docs/POSTGRESQL_PERSISTENCE_PLAN.md`.
- Istorijski pre-match quote model mora koristiti quote series i immutable snapshots; postojeći single-row identity model nije dovoljan.
- Live/in-play kvote nisu deo QuantBet obuhvata.

## Dokumentacija

- `docs/QUOTE_USE_CASES.md`
- `docs/PERSISTENCE_BOUNDARY.md`
- `docs/SQLITE_PERSISTENCE.md`
- `docs/POSTGRESQL_PERSISTENCE_PLAN.md`
- `docs/HISTORICAL_PREMATCH_QUOTES_DESIGN.md`
- `docs/ITERATION_LOG.md`
- `docs/APPLICATION_COMPOSITION.md`
- `docs/CONFIGURATION.md`
- `docs/HTTP_TRANSPORT.md`
- `docs/API_FOOTBALL_SERVICE.md`
- `docs/RETRY_POLICY.md`
- `docs/API_BUDGET.md`
- `docs/API_FOOTBALL_CACHE.md`
- `docs/PHASE_I_UNIVERSE_SCOPE.md`
- `docs/VALUE_PICK_EVALUATION.md`
- `docs/FIXTURE_DISCOVERY_CONTRACT.md`
- `docs/SCOPED_FIXTURE_DISCOVERY.md`
- `docs/API_FOOTBALL_FIXTURE_ADAPTER.md`
- `docs/PICK_REGISTRATION.md`
- `docs/RESEARCH_SECTOR_PLAN.md`

## Sledeći korak

Pre implementacije istorijskih quote snapshot-a potrebno je eksplicitno odobriti dizajn iz `docs/HISTORICAL_PREMATCH_QUOTES_DESIGN.md`, naročito:

1. history-aware repository contract;
2. snapshot deduplication ključ;
3. kickoff/closing policy;
4. tretman zakašnelo pristiglih observacija;
5. veza između `PickRegistration` i `QuoteSnapshot`;
6. PostgreSQL šema i transaction strategija.

Nakon odobrenja sledi implementacija → testovi → dokumentacija → CI verifikacija.

## Pravila rada

- Jedna mala implementaciona celina po koraku.
- Testovi i CI verifikacija pre prelaska na sledeći korak.
- Svaka završena celina mora imati odgovarajuću `.md` dokumentaciju.
- Svaka relevantna iteracija mora biti zabeležena u `docs/ITERATION_LOG.md` ljudski čitljivim opisom i timestamp-om.
- `docs/PROGRESS.md` sadrži sažetak većih završenih celina, dok `docs/ITERATION_LOG.md` sadrži detalje manjih koraka.
- Quant matematika ostaje zaključana bez nove regresione verifikacije.
- Provider-specific strukture ne ulaze u quant sloj.
- Fixture-universe politika ostaje odvojena od quant izračunavanja i quote normalizacije.
- Research eksperimenti ne menjaju production logiku implicitno; svaka promena mora biti verzionisana, validirana i eksplicitno promovisana.
