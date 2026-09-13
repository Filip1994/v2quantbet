# QuantBet — Progress

## Trenutno stanje

Quant/domain foundation je izgrađen i testiran: Dixon–Coles baseline, golden-master zaštita, javni quant API, canonical quote modeli, market snapshot validacija i provider-neutral quote normalizacija.

Provider-neutral quote adapter contract je definisan, eksportovan i pokriven testovima. CI za tu celinu je uspešan.

## Završeno u aktuelnoj celini

- Dodat `build_market_snapshot()` kao mali orchestration sloj između provider payload-a i domena.
- Builder koristi `ProviderQuoteAdapter` contract i podrazumevani `NormalizingProviderQuoteAdapter`.
- Adaptirani payload-i se skupljaju u tuple canonical quote-ova.
- Formiranje snapshot-a delegira validaciju na `MarketSnapshot.from_quotes()`.
- Dodat je test za kompletan OU_25 par, nekompletan market i prazan input.
- Builder je eksportovan kroz `h2h.odds`.
- Definisan je provider-neutral ingestion ugovor u `docs/ODDS_INGESTION_CONTRACT.md`.
- Precizirani su fixture/bookmaker identity, canonical market mapping, `observed_at`, idempotency, duplicate/conflict i rejection pravila.

## Sledeći korak

Implementirati i testirati prvi konkretan provider adapter za API-Football, uz reprezentativne payload fixture-e i strogo odvajanje provider-specific strukture od canonical domain sloja.

## Pravila rada

- Jedna mala implementaciona celina po koraku.
- Testovi i CI verifikacija pre prelaska na sledeći korak.
- Quant matematika ostaje zaključana bez nove regresione verifikacije.
- Provider-specific strukture ne ulaze u quant sloj.
