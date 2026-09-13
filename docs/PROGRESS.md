# QuantBet — Production Readiness Roadmap

Ovaj dokument sadrži samo ono što je još potrebno da bi QuantBet postao production-ready u skladu sa `docs/QUANTBET_GOALS.md`.

## Trenutna granica

Quant/domain foundation je izgrađen i testiran: Dixon–Coles baseline, golden-master zaštita, javni quant API, canonical quote modeli, market snapshot validacija i provider-neutral quote normalizacija.

Provider-neutral quote adapter contract je sada definisan, eksportovan i pokriven testovima. Poslednji CI run za ovu celinu je `completed` / `success`.

Production sistem još nije završen kao end-to-end celina.

## 1. Završiti canonical odds pipeline

- [x] Definisan provider-neutral `ProviderQuoteAdapter` contract.
- [x] Dodata početna `NormalizingProviderQuoteAdapter` implementacija.
- [x] Dodat test koji proverava canonical quote rezultat i propagaciju validacije.
- [ ] Završiti ugovor za formiranje `MarketSnapshot` iz normalizovanih `CanonicalQuote` observacija.
- [ ] Uvesti konkretan API-Football adapter tek iza provider-neutral boundary-ja.
- [ ] Precizno definisati:
  - fixture identity;
  - bookmaker identity;
  - market/selection mapping;
  - `observed_at`, provider timestamp i `ingested_at` semantiku;
  - duplicate observation i idempotency pravila;
  - ponašanje za nepoznate ili nepotpune provider vrednosti.
- [ ] Dodati integration testove sa reprezentativnim provider payload-ima.

## 2. Implementirati persistence sloj

- Definisati PostgreSQL schema i migracije.
- Implementirati repository interfejse i PostgreSQL adapter.
- Sačuvati immutable odds observations bez gubitka istorije.
- Omogućiti efikasno čitanje trenutnih, istorijskih i closing kvota.
- Uvesti unique constraints/indexe za identity i idempotentni ingestion.
- Dodati repository/integration testove protiv PostgreSQL-a.
- Definisati backup, restore i migration procedure.

## 3. Implementirati fixture i odds ingestion

- Preuzimati relevantne fixture-e za narednih 72 sata.
- Uvesti scheduling i kontrolisani polling.
- Razdvojiti fixture ingestion od odds ingestion-a.
- Uvesti timeout, retry, backoff i rate-limit ponašanje.
- Uvesti idempotentno ponavljanje job-ova.
- Sačuvati raw provider response ili definisati odvojenu arhivsku strategiju.
- Uvesti data-quality kontrole za stale, missing i contradictory podatke.

## 4. Implementirati quant evaluation i value engine

- Povezati validne market snapshot-e sa quant modelom.
- Definisati precizan obračun implied probability i value.
- Razdvojiti model probability, implied probability, value, expected CLV i realized CLV.
- Uvesti verzionisanje modela i konfiguracije.
- Dodati testove za granice, rounding, determinism i market-specific pravila.

## 5. Implementirati decision, risk i pick registry

- Definisati decision contract za prihvatanje/odbijanje kandidata.
- Implementirati eksplicitne risk filtere i limite.
- Definisati immutable pick zapis sa model/config verzijom, kvotom, value i risk metapodacima.
- Uvesti idempotency i zaštitu od duplog kreiranja pick-a.
- Dodati unit i integration testove za decision/risk/pick lifecycle.

## 6. Implementirati praćenje pick-a i CLV

- Uvesti periodično praćenje kvota nakon objave pick-a.
- Definisati closing cutoff i validnu closing referencu.
- Implementirati realized CLV tek nakon dostupne i validne closing reference.
- Obezbediti audit trail i reproducibilan obračun.

## 7. Bulletin i read-side API

- Implementirati dnevni bulletin sa jasnim statusima, timestamp-ima i verzijama.
- Definisati read/query service sloj iznad persistence-a.
- Implementirati API za fixture-e, market state, picks, odds history, CLV i health status.
- Dashboard napraviti kao read-side klijent API-ja.
- Dodati API contract testove i autentikaciju/autorizaciju gde je potrebna.

## 8. Operativna production spremnost

- Implementirati health/readiness endpoint-e.
- Uvesti strukturisane logove, metrike i error reporting.
- Pratiti ingestion lag, provider errors, stale data, job failures i database health.
- Uvesti alerting za kritične kvarove.
- Definisati secrets/config management van Git-a.
- Uvesti deployment proceduru, rollback i migracije bez gubitka podataka.
- Proveriti Railway resource limits, persistent storage i backup/restore.
- Dodati end-to-end smoke test u deployment pipeline.
- Definisati runbook za oporavak od provider, worker i database problema.

## 9. Production acceptance kriterijumi

Pre proglašenja production readiness-a moraju biti dokazani:

- end-to-end tok od provider payload-a do sačuvanog canonical snapshot-a;
- reproducibilno čitanje odds istorije;
- idempotentan ingestion i bezbedni retry-i;
- validan pick lifecycle;
- reproducibilan realized CLV obračun;
- testirana PostgreSQL migracija i restore procedura;
- funkcionalni health/metrics/alerting mehanizmi;
- zeleni unit, integration i end-to-end testovi;
- dokumentovan deployment i incident recovery postupak;
- bez tajni u repozitorijumu.

## Redosled rada

1. MarketSnapshot contract.
2. Provider adapter contract i test payload-i.
3. PostgreSQL schema, migracije i repository.
4. Fixture/odds ingestion sa retry/idempotency pravilima.
5. Quant evaluation i value engine.
6. Decision/risk/pick registry.
7. Pick monitoring i realized CLV.
8. Bulletin i API.
9. Observability, deployment hardening i production acceptance testovi.

## Pravila za nastavak

- Jedna mala implementaciona celina po koraku.
- Testovi i CI verifikacija pre prelaska na sledeći korak.
- Quant matematika ostaje zaključana bez nove golden-master/regresione verifikacije.
- Provider-specific strukture ne ulaze u quant sloj.
- Research infrastruktura i dodatna tržišta ostaju van aktivnog production scope-a dok ne postoji eksplicitna odluka.
