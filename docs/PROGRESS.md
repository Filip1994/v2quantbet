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

## Sledeći korak

Proveriti CI za duplicate/conflict celinu. Nakon toga razmotriti persistence boundary; quant sloj ostaje odvojen od provider-specific struktura.

## Pravila rada

- Jedna mala implementaciona celina po koraku.
- Testovi i CI verifikacija pre prelaska na sledeći korak.
- Quant matematika ostaje zaključana bez nove regresione verifikacije.
- Provider-specific strukture ne ulaze u quant sloj.
