# QuantBet — Progress

## 2026-09-23 — Issue #15 operator pick tracking

- Registered picks derive `PLAYED` by default; there is no `UNREPORTED` state.
- Explicit PLAYED/SKIPPED changes are append-only, idempotent and linked only to `pick_id`.
- Actual/operator bankroll excludes SKIPPED picks while system settlement, CLV and model
  history remain complete.
- Dashboard shows system status and operator status separately, with authenticated controls
  and played/skipped summary totals.

## 2026-09-23 — Issue #14 multi-bookmaker execution

- Preliminary production requests ingest Bet365 (8), 1xBet (11) and Superbet (34) together.
- Exact-semantic eligible prices are ranked; mandatory final verification falls back through
  ranked approved candidates and rejects when none remains.
- Monitoring targets the bookmaker registered on each pick, preserving same-book Closing/CLV.
- Metrics cover compared quotes, preliminary/final refreshes, fallbacks, no-valid outcomes
  and wins by bookmaker.
- Dashboard/API distinguish Pick, same-book current, best current and same-book Closing with
  accessible movement cues, bookmaker badges and glossary.

## Trenutno stanje

QuantBet više nije samo repository-level implementacija: **production Railway servis je aktivan i live runtime je verifikovan**.

Na dan **2026-09-23** Railway production servis `quantbet-engine` deployuje `Filip1994/v2quantbet:main`, koristi `python -m h2h.entrypoint`, PostgreSQL kao durable source of truth i single-leader scheduler. Deploy commita `96bb0a943674783e9035449c43150ad1113355bd` je potvrđen kao uspešan, a runtime je preuzeo production leadership.

Live scheduler izvršava:

- fixture discovery;
- model lifecycle / training coverage;
- opportunity evaluation;
- final quote verification;
- pick registration;
- Daily Bulletin;
- registered-pick monitoring / closing;
- result acquisition / settlement.

Production logovi su potvrdili da opportunity pipeline ne staje na evaluaciji: ciklusi su već emitovali **`registered_picks > 0`**, odnosno sistem je autonomno registrovao realne production pickove.

To potvrđuje sledeći end-to-end put:

`discovery → model selection/prediction → odds/value evaluation → eligibility/risk → final quote verification → durable pick registration`

Pick-monitoring, closing, result-settlement, bankroll-accounting i realized-CLV komponente su implementirane, PostgreSQL-persistirane i production-schedulovane. Međutim, ovaj dokument ne tvrdi da je već prikupljen reprezentativan broj settled production pickova niti da je profitabilnost dokazana.

## Quant i provider foundation

Quant/domain foundation ostaje izgrađen i testiran: Dixon–Coles baseline, golden-master zaštita, javni quant API, canonical quote modeli, market snapshot validacija i provider-neutral quote normalizacija.

API-Football integracija je razdvojena po slojevima:

- canonical fixture discovery;
- provider identity validation;
- odds transport i normalization;
- immutable quote-history ingestion;
- trusted FT-only historical acquisition za model training provenance;
- result acquisition za settlement lifecycle.

Fixture identity path je canonical: API-Football discovery dodeljuje `api-football:<id>`, čuva odvojeni numeric provider ID za transport i authoritative ordered provider home/away team IDs. Odds ingestion proverava da odgovor pripada traženom provider fixture-u pre flattening-a.

## Prediction i model lifecycle

Prediction boundary je fixture-bound: authoritative `Fixture` se prevodi u kontrolisani `PredictionTarget`, proverava se `team_id_namespace`, home/away redosled ostaje stabilan, a valuation zahteva exact canonical fixture equality.

Production model lifecycle sada uključuje:

- PostgreSQL model-version persistence;
- active-model selection/loading;
- trusted API-Football historical dataset acquisition;
- scheduled training/activation worker;
- production fixture-to-model execution.

Model coverage ipak nije uniforman. Runtime trenutno povremeno beleži `InsufficientTrainingDataError` za pojedine competition/season scope-ove, pa je model lifecycle **production-active, ali coverage još nije kompletan**.

## Odds, value i registracija pickova

History-aware ingestion pretvara canonical quote opažanja u stabilne `QuoteSeries` entitete i immutable `QuoteSnapshot` zapise.

Production opportunity worker radi:

1. izbor due fixture-a;
2. acquisition i persistence kvota;
3. model prediction;
4. canonical market/selection probability mapping;
5. de-vig/value evaluation;
6. eligibility/freshness/quality proveru;
7. risk/stake proveru;
8. mandatory final quote verification;
9. durable decision i pick registration.

Final quote verification je fail-closed. Stale provider quote ne postaje automatski pick-time cena; sistem radi bounded refresh/retry i može da odbije priliku ako validna finalna observacija nije dostupna.

Live runtime je već potvrdio production registraciju pickova.

## Bankroll, monitoring, settlement i CLV

Bankroll state koristi durable PostgreSQL accounting/ledger putanju. Registration rezerviše stake kroz kontrolisanu risk/stake politiku i open-exposure ograničenja.

Za registrovane pickove postoje:

- restart-safe monitoring state;
- current-quote refresh;
- immutable closing finalization;
- result acquisition state;
- settlement event persistence;
- payout/loss/void accounting;
- bankroll ledger integracija;
- realized CLV persistence kada postoje validni entry i closing checkpoint-i.

Monitoring i results worker-i su aktivno uključeni u production scheduler. Implementacija i wiring su završeni; reprezentativan production settlement sample još nije dokumentovan kao završen eksperiment.

## Daily Bulletin i read surfaces

Daily Bulletin više nije samo read-model plan. Postoji durable daily snapshot/membership persistence i scheduler worker sa Europe/Belgrade vremenskom semantikom.

Production HTTP servis trenutno izlaže:

- `/livez`;
- `/readyz`;
- authenticated `/dashboard`;
- authenticated `/api/picks`.

Dashboard je read-only i koristi durable production stanje. Trenutna implementacija je minimalna; kompletan V1 presentation scope iz `docs/DASHBOARD_SPEC.md` još se dovršava.

## Završeno

- Quant/domain foundation i golden-master regresiona zaštita.
- Canonical quote modeli i market snapshot validacija.
- Provider-neutral quote adapter contract.
- API-Football flattening, normalization, deduplication i conflict handling.
- Canonical fixture identity, provider fixture reference i ordered provider team identity.
- Fail-closed API-Football response fixture identity validation.
- In-memory i PostgreSQL quote-history persistence sa idempotentnim upisom i conflict rejection pravilima.
- PostgreSQL migrations i production runtime composition.
- Environment konfiguracija, HTTP transport, retry/rate-limit handling i API budget accounting.
- Phase I competition-scope filter.
- Deterministička value evaluacija, implied/de-vig probability i EV/edge logika.
- Fixture-bound Dixon–Coles production prediction.
- FT-only API-Football completed-match acquisition sa provenance granicom.
- PostgreSQL model lifecycle i scheduled training/activation.
- Eligibility/freshness/quality registration gate.
- Risk/stake policy i bankroll exposure kontrola.
- Mandatory final quote verification.
- Durable decision i immutable registered-pick repository sa duplicate protection.
- Production opportunity worker koji je runtime-verifikovano registrovao pickove.
- Daily Bulletin durable snapshot i worker.
- Pick-specific monitoring i immutable closing finalization.
- Result acquisition, settlement accounting i realized-CLV persistence path.
- Production orchestrator sa leader election, readiness/liveness i restart-safe worker state-om.
- Authenticated read-only dashboard/picks HTTP surface.
- Railway production deployment na `main`.
- Testovi i CI zaštita za navedene celine.

## Trenutni operativni rizici / ograničenja

### 1. Model coverage

Neki league/season scope-ovi još nemaju dovoljan istorijski dataset za pouzdan fit. Sistem ih fail-closed ne forsira kroz production prediction.

### 2. Stale provider odds

API-Football može vratiti staru odds observaciju. To trenutno uzrokuje retry/final-verification cikluse, povećava latency i može da eliminiše priliku koja bi inače prošla value threshold.

Ovo je trenutno jedan od glavnih production bottleneck-a i treba ga pratiti kroz:

- stale-quote rate;
- final-verification rejection rate;
- API calls per registered pick;
- opportunity latency;
- broj propuštenih fixture-a zbog freshness granice.

### 3. Performance evidence

Sistem proizvodi pickove, ali broj production ishoda još nije dovoljan za tvrdnju o održivoj profitabilnosti.

Glavni naredni validation metrics su:

- realized CLV;
- realized ROI/P&L;
- calibration;
- performance po marketu;
- performance po competition/model version-u;
- stale-data attrition;
- pick frequency i exposure distribution.

Model ili policy ne treba optimizovati na osnovu malog početnog production sample-a bez unapred definisane evaluacione procedure.

### 4. Dashboard completeness

Dashboard endpoint postoji i radi kao read-only operational surface, ali još ne prikazuje kompletan Dashboard V1 scope iz `docs/DASHBOARD_SPEC.md`.

## Arhitektonske odluke

- Railway PostgreSQL je canonical production persistence path.
- Railway `quantbet-engine` je potvrđen live production servis.
- PostgreSQL quote, decision, pick, monitoring, settlement i accounting records su backend source of truth; UI ih ne menja.
- Istorijski pre-match quote model koristi quote series i immutable snapshots.
- Live/in-play kvote nisu deo QuantBet obuhvata.
- Historical pick i closing facts se ne prepisuju kasnijim observacijama.
- Low-level `DixonColesModel.fit()` namespace ostaje caller claim, dok production provenance bridge izvodi namespace iz validiranog provider dataset-a.
- Dashboard je read-only reporting/operational surface, ne trading interface.

## Dokumentacija

Detaljni ugovori i planovi ostaju u specijalizovanim dokumentima, uključujući:

- `docs/FIXTURE_DISCOVERY_CONTRACT.md`
- `docs/ODDS_INGESTION_CONTRACT.md`
- `docs/API_FOOTBALL_TRAINING.md`
- `docs/PREDICTION_TARGETING_CONTRACT.md`
- `docs/VALUE_DECISION_CONTRACT.md`
- `docs/PICK_REGISTRATION.md`
- `docs/PICK_MONITORING_ODDS_LIFECYCLE.md`
- `docs/RESULTS_SETTLEMENT_PERFORMANCE.md`
- `docs/DASHBOARD_SPEC.md`
- `docs/DASHBOARD_DESIGN.md`
- `docs/quant-golden-master.md`

## Implementation roadmap

1. API-Football fixture discovery, canonical identity i ordered provider team IDs — **IMPLEMENTED / VERIFIED**
2. API-Football odds transport, canonical quotes i response identity validation — **IMPLEMENTED / VERIFIED**
3. PostgreSQL quote-history ingestion i discovery-driven runtime — **IMPLEMENTED / VERIFIED**
4. Dixon–Coles matematika i numerical regression baseline — **IMPLEMENTED / VERIFIED**
5. Canonical market/selection probability mapping i value formule — **IMPLEMENTED / VERIFIED**
6. Authoritative target, namespace compatibility i identity-safe valuation — **IMPLEMENTED / VERIFIED**
7. Production completed-match acquisition sa API-Football provenance — **IMPLEMENTED / VERIFIED (FT ONLY)**
8. Training orchestration i model artifact/version lifecycle — **IMPLEMENTED / PRODUCTION ACTIVE; COVERAGE PARTIAL**
9. Durable fixture metadata i prediction/value provenance — **IMPLEMENTED FOR PRODUCTION PATH; FURTHER AUDIT ENRICHMENT POSSIBLE**
10. Production fixture-to-model execution — **IMPLEMENTED / RUNTIME VERIFIED**
11. Eligibility structures i registration gate — **IMPLEMENTED / RUNTIME VERIFIED**
12. Freshness/quality/de-vig/risk/stake policy — **IMPLEMENTED / RUNTIME ACTIVE**
13. Durable decision/pick repository i duplicate protection — **IMPLEMENTED / RUNTIME VERIFIED**
14. Daily Bulletin durable registered-pick projection — **IMPLEMENTED / PRODUCTION SCHEDULED**
15. Pick-specific monitoring i immutable closing finalization — **IMPLEMENTED / PRODUCTION SCHEDULED**
16. Match-result acquisition, settlement i realized CLV — **IMPLEMENTED / PRODUCTION SCHEDULED; LIVE SAMPLE MATURING**
17. Production end-to-end composition i operational pilot — **LIVE / ACTIVE PILOT**
18. Dashboard V1 completion — **PARTIAL; MINIMAL READ-ONLY SURFACE LIVE**

## Pravila rada

- Jedna mala implementaciona celina po koraku.
- Testovi i CI verifikacija pre prelaska dalje.
- Svaka završena celina mora imati odgovarajuću dokumentaciju.
- Quant matematika ostaje zaključana bez nove regresione verifikacije.
- Provider-specific strukture ne ulaze u quant sloj.
- Fixture-universe politika ostaje odvojena od quant izračunavanja i quote normalizacije.
- Research eksperimenti ne menjaju production logiku implicitno; svaka promena mora biti verzionisana, validirana i eksplicitno promovisana.
- Production performance zaključci moraju biti zasnovani na durable out-of-sample evidence-u, ne na malom početnom broju pickova.
