# QuantBet — Progress

## Trenutno stanje

Quant/domain foundation je izgrađen i testiran: Dixon–Coles baseline, golden-master zaštita, javni quant API, canonical quote modeli, market snapshot validacija i provider-neutral quote normalizacija.

Provider-neutral quote adapter contract, API-Football adapter, ingestion, persistence, configuration, HTTP transport, API-Football client i application service su implementirani kao odvojeni slojevi.

Prvi value-evaluation sloj je implementiran: model-vs-market poređenje računa implied probability, probability gap i expected value uz validaciju model probability granica.

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
- Testovi i dokumentacija za svaku navedenu celinu.

## Dokumentacija

- `docs/QUOTE_USE_CASES.md`
- `docs/PERSISTENCE_BOUNDARY.md`
- `docs/SQLITE_PERSISTENCE.md`
- `docs/APPLICATION_COMPOSITION.md`
- `docs/CONFIGURATION.md`
- `docs/HTTP_TRANSPORT.md`
- `docs/API_FOOTBALL_SERVICE.md`
- `docs/RETRY_POLICY.md`
- `docs/API_BUDGET.md`
- `docs/API_FOOTBALL_CACHE.md`
- `docs/PHASE_I_UNIVERSE_SCOPE.md`
- `docs/VALUE_PICK_EVALUATION.md`

## Sledeći korak

Povezati competition-scope filter sa fixture discovery/use-case slojem, zatim implementirati immutable pick registration i generisanje dnevnog biltena kao prvi bulletin vertical slice.

## Pravila rada

- Jedna mala implementaciona celina po koraku.
- Testovi i CI verifikacija pre prelaska na sledeći korak.
- Quant matematika ostaje zaključana bez nove regresione verifikacije.
- Provider-specific strukture ne ulaze u quant sloj.
- Fixture-universe politika ostaje odvojena od quant izračunavanja i quote normalizacije.
