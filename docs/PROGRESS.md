# QuantBet — Progress

## Trenutno stanje

Quant/domain foundation je izgrađen i testiran: Dixon–Coles baseline, golden-master zaštita, javni quant API, canonical quote modeli, market snapshot validacija i provider-neutral quote normalizacija.

Provider-neutral quote adapter contract, API-Football adapter, ingestion, persistence, configuration, HTTP transport, API-Football client i application service su implementirani kao odvojeni slojevi.

Prvi value-evaluation sloj je implementiran: model-vs-market poređenje računa implied probability, probability gap i expected value uz validaciju model probability granica.

Fixture discovery foundation je uveden kroz canonical `Fixture` model, provider-neutral `FixtureDiscovery` contract, `ScopedFixtureDiscovery` use-case i API-Football fixture adapter sa hardening validacijom.

History-aware ingestion pretvara canonical quote opažanja u stabilne `QuoteSeries` entitete i immutable `QuoteSnapshot` zapise. PostgreSQL runtime composition, restart-safe series lookup, discovery-driven polling i worker entrypoint su implementirani i testirani. Live Railway deployment i operational pilot nisu potvrđeni ovim repozitorijumom.

Fixture identity path je canonical: API-Football discovery dodeljuje `api-football:<id>`, čuva odvojeni numeric provider ID za transport i authoritative ordered provider home/away team IDs. Odds ingestion proverava da response pripada traženom provider fixture-u pre flattening-a.

Prediction boundary je fixture-bound: authoritative `Fixture` se pretvara u kontrolisani `PredictionTarget`, proverava se `team_id_namespace`, home/away redosled ostaje stabilan, a valuation zahteva exact canonical fixture equality.

Ovaj prediction path ne predstavlja production training pipeline. Repository još nema trusted API-Football completed-match acquisition, training adapter ni dokaz da caller-supplied namespace odgovara stvarnom poreklu training records.

## Završeno

- Quant/domain foundation i regresiona zaštita.
- Canonical quote modeli i market snapshot validacija.
- Provider-neutral quote adapter contract.
- API-Football flattening, normalization, deduplication i conflict handling.
- Canonical fixture identity, provider fixture reference i ordered provider team identity.
- Fail-closed API-Football response fixture identity validation pre quote flattening-a.
- In-memory i PostgreSQL quote-history persistence sa idempotentnim upisom i atomskim odbijanjem konflikata.
- Quote ingestion use case, PostgreSQL migrations i application composition/lifecycle.
- Environment konfiguracija, provider-neutral HTTP transport, retry/rate-limit handling, API budget i fixture-level cache.
- Phase I competition-scope filter sa stabilnim rejection reason kodovima.
- Deterministička ValuePick evaluacija: implied probability, probability gap i expected value.
- Immutable `PickRegistration` model sa `PickStatus` lifecycle enumeracijom.
- Provider-neutral fixture discovery, scoped discovery i API-Football fixture adapter.
- Provider-neutral `HistoryQuotePollingJob`, discovery-driven polling i worker/runtime entrypoint.
- Fixture-bound Dixon–Coles prediction target, model namespace compatibility i identity-safe value evaluation.
- Testovi i dokumentacija za navedene celine.
- Jasna granica između operativnog Daily Bulletin screeninga i budućeg Research sektora.
- Research boundary i plan, bez implicitnog menjanja production logike.

## Arhitektonske odluke

- Railway PostgreSQL je potvrđena ciljna production baza; repository ne tvrdi da je live deployment izvršen.
- PostgreSQL quote-history adapter je implementiran iza provider-neutral ugovora.
- SQLite ostaje privremeno dostupan za legacy testove i migration work; nije odobreni Railway production path.
- Local PostgreSQL integration testovi zahtevaju dostupnu PostgreSQL instancu; CI workflow je zasebna verifikaciona putanja.
- Istorijski pre-match quote model koristi quote series i immutable snapshots.
- Live/in-play kvote nisu deo QuantBet obuhvata.
- `team_id_namespace` na modelu je compatibility claim, ne dokaz porekla training podataka.

## Dokumentacija

Detaljni ugovori i planovi ostaju u specijalizovanim dokumentima, uključujući `docs/FIXTURE_DISCOVERY_CONTRACT.md`, `docs/ODDS_INGESTION_CONTRACT.md`, `docs/PREDICTION_TARGETING_CONTRACT.md`, `docs/quant-api-contract.md`, `docs/POSTGRESQL_PERSISTENCE_PLAN.md`, `docs/VALUE_DECISION_CONTRACT.md` i `docs/RESEARCH_SECTOR_PLAN.md`.

## Implementation roadmap

1. API-Football fixture discovery, canonical identity i ordered provider team IDs — **IMPLEMENTED / VERIFIED**
2. API-Football odds transport, canonical quotes i response identity validation — **IMPLEMENTED / VERIFIED**
3. PostgreSQL quote-history ingestion i discovery-driven worker — **IMPLEMENTED / VERIFIED**
4. Dixon–Coles matematika i numerical regression baseline — **IMPLEMENTED / VERIFIED**
5. Canonical market/selection probability mapping i value formule — **IMPLEMENTED / VERIFIED**
6. Authoritative target, namespace compatibility i identity-safe valuation — **IMPLEMENTED / VERIFIED**
7. Production completed-match acquisition sa eksplicitnim API-Football provenance — **NOT IMPLEMENTED; NEXT DEPENDENCY**
8. Training validation/orchestration i model artifact/version lifecycle — **PARTIAL / BLOCKED**
9. Durable fixture metadata i prediction/value provenance — **PARTIAL / NOT COMPLETE**
10. Production fixture-to-model execution — **BLOCKED** training putanjom
11. Eligibility structures i registration gate — **PARTIAL**
12. Actual eligibility/freshness/quality/de-vig/risk/stake policy — **NOT IMPLEMENTED**
13. Durable decision/pick repository i duplicate protection — **NOT COMPLETE**
14. Daily Bulletin selection/formatting/delivery — **NOT COMPLETE**
15. Pick-specific monitoring i designated closing capture — **PARTIAL / NOT COMPLETE**
16. Match-result acquisition, settlement i realized CLV — **NOT COMPLETE**
17. Production end-to-end composition i operational pilot — **BLOCKED** prethodnim runtime komponentama

## Pravila rada

- Jedna mala implementaciona celina po koraku.
- Testovi i CI verifikacija pre prelaska na sledeći korak.
- Svaka završena celina mora imati odgovarajuću `.md` dokumentaciju.
- Quant matematika ostaje zaključana bez nove regresione verifikacije.
- Provider-specific strukture ne ulaze u quant sloj.
- Fixture-universe politika ostaje odvojena od quant izračunavanja i quote normalizacije.
- Research eksperimenti ne menjaju production logiku implicitno; svaka promena mora biti verzionisana, validirana i eksplicitno promovisana.
