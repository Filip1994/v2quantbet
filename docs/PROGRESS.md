# QuantBet — Progress

## Trenutno stanje

Quant/domain foundation je izgrađen i testiran: Dixon–Coles baseline, golden-master zaštita, javni quant API, canonical quote modeli, market snapshot validacija i provider-neutral quote normalizacija.

Provider-neutral quote adapter contract je definisan, eksportovan i pokriven testovima. CI za tu celinu je uspešan.

Prvi API-Football quote adapter je implementiran na osnovu stvarnog `/odds` odgovora, uz izolovane adapter testove. CI verifikacija ove nove celine je još potrebna.

## Završeno u aktuelnoj celini

- Dodat `build_market_snapshot()` kao mali orchestration sloj između provider payload-a i domena.
- Builder koristi `ProviderQuoteAdapter` contract i podrazumevani `NormalizingProviderQuoteAdapter`.
- Adaptirani payload-i se skupljaju u tuple canonical quote-ova.
- Formiranje snapshot-a delegira validaciju na `MarketSnapshot.from_quotes()`.
- Dodat je test za kompletan OU_25 par, nekompletan market i prazan input.
- Builder je eksportovan kroz `h2h.odds`.
- Definisan je provider-neutral ingestion ugovor u `docs/ODDS_INGESTION_CONTRACT.md`.
- Precizirani su fixture/bookmaker identity, canonical market mapping, `observed_at`, idempotency, duplicate/conflict i rejection pravila.
- Dodat `ApiFootballQuoteAdapter` za BTTS i OU 2.5 quote vrednosti.
- Dodat test za stvarni API-Football format: fixture, bookmaker, bet, value i update polja.
- Adapter je eksportovan kroz `h2h.odds`.

## Sledeći korak

Pokrenuti i potvrditi CI za API-Football adapter, zatim dodati ingestion funkciju koja iz kompletnog API-Football `/odds` odgovora izdvaja podržane bookmaker/bet/value kombinacije.

## Pravila rada

- Jedna mala implementaciona celina po koraku.
- Testovi i CI verifikacija pre prelaska na sledeći korak.
- Quant matematika ostaje zaključana bez nove regresione verifikacije.
- Provider-specific strukture ne ulaze u quant sloj.
