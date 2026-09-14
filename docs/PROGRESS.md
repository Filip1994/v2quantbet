# QuantBet — Progress

## Trenutno stanje

Quant/domain foundation je izgrađen i testiran: Dixon–Coles baseline, golden-master zaštita, javni quant API, canonical quote modeli, market snapshot validacija i provider-neutral quote normalizacija.

Provider-neutral quote adapter contract je definisan, eksportovan i pokriven testovima. API-Football adapter i ingestion sloj su implementirani i provereni kroz CI.

## Završeno u aktuelnoj celini

- Dodat `iter_api_football_quote_payloads()` za flattenovanje kompletnog API-Football `/odds` odgovora.
- Dodat `ingest_api_football_odds()` koji provider payload-e pretvara u `CanonicalQuote` objekte.
- Dodat `build_api_football_market_snapshots()` koji quote-ove grupiše po fixture/bookmaker/market/observation timestamp kontekstu.
- Formiranje snapshot-a delegira validaciju na `MarketSnapshot.from_quotes()`.
- API-Football ingestion funkcije su eksportovane kroz `h2h.odds`.
- Dodati testovi za flattenovanje, ingestiju, snapshot construction i malformed provider grane.
- Dodat `deduplicate_quotes()` za idempotentno uklanjanje identičnih ponovljenih quote-ova.
- Dodat `QuoteConflictError` za eksplicitno odbijanje različitih opažanja sa istim canonical identity ključem.
- Dodat test za identične duplikate, različite identitete i konfliktne quote-ove.
- Dodat provider-neutral `QuoteRepository` contract.
- Dodat `InMemoryQuoteRepository` sa idempotentnim save ponašanjem i atomskim conflict handling-om.
- Dodati testovi za čuvanje, query po fixture-u, identične duplikate i konflikt bez parcijalnog upisa.
- Dodat `docs/PERSISTENCE_BOUNDARY.md` sa pravilima persistence sloja.
- Dodat `QuoteIngestionService` kao provider-neutral read/write application use case.
- Dodati testovi za ingestiju, fixture-scoped read i full read ponašanje servisa.
- Dodat `docs/QUOTE_USE_CASES.md` sa granicama odgovornosti application sloja.
- Dodat `SQLiteQuoteRepository` sa automatskom šemom, round-trip rekonstrukcijom, idempotentnim upisom i atomskim odbijanjem konflikata.
- Dodati testovi za SQLite round-trip, query po fixture-u, identične duplikate, atomic conflict handling i ponovno otvaranje baze.
- Dodat `docs/SQLITE_PERSISTENCE.md` sa ugovorom i načinom korišćenja SQLite adaptera.
- SQLite persistence celina je proverena kroz CI; nakon ispravke Ruff import reda CI je zelen.
- Dodat `build_sqlite_quote_service()` kao application composition root koji povezuje SQLite repository i `QuoteIngestionService` bez provider coupling-a.
- Dodat test composition root-a i `docs/APPLICATION_COMPOSITION.md`.
- Dodat `SQLiteQuoteApplication` sa eksplicitnim `close()` lifecycle ugovorom i context-manager podrškom.
- Dodati testovi za zatvaranje konekcije, automatsko zatvaranje kroz `with` blok i ponovno otvaranje baze.
- Ažurirana dokumentacija application composition sloja sa production-facing lifecycle primerom.
- Dodat `ApplicationSettings` i `load_settings()` za validaciju `API_FOOTBALL_KEY` i SQLite putanje iz environment-a.
- Dodat settings-based application builder bez unošenja provider tajni u quant ili persistence sloj.
- Dodati testovi za default putanju, praznu/nedostajuću tajnu, trimovanje vrednosti i redaction kroz `repr()`.
- Dodat `docs/CONFIGURATION.md` sa production konfiguracionim ugovorom.

## Sledeći korak

Proveriti CI za configuration/startup boundary celinu. Nakon zelenog CI-ja preći na sledeću production-readiness granicu.

## Pravila rada

- Jedna mala implementaciona celina po koraku.
- Testovi i CI verifikacija pre prelaska na sledeći korak.
- Quant matematika ostaje zaključana bez nove regresione verifikacije.
- Provider-specific strukture ne ulaze u quant sloj.
