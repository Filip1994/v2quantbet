# QuantBet — Data Clarification

**Status:** dizajn dokumenta, bez runtime implementacije  
**Vreme kreiranja:** 2026-09-14 14:43:00 +02:00  
**Svrha:** jednostavan pregled toga koje informacije QuantBet prima, šta sa njima radi, gde ih čuva i u kom trenutku nastaju.

## 1. Osnovno pravilo

Svaka informacija koju QuantBet primi ili izračuna mora imati jasno mesto u sistemu.

Za svaku informaciju moramo moći da odgovorimo na četiri pitanja:

1. Odakle je došla?
2. Kada je primljena ili izračunata?
3. Gde je sačuvana?
4. Za šta se kasnije koristi?

Ako informacija nema poznato poreklo, timestamp i mesto čuvanja, ne sme se tretirati kao pouzdan production podatak.

## 2. Glavni tok podataka

```text
API provider
    ↓
HTTP transport
    ↓
Provider client
    ↓
Provider adapter / normalizacija
    ↓
Canonical domain model
    ↓
Validation
    ↓
Application service
    ↓
Persistence repository
    ↓
Historical storage
    ↓
Value evaluation / Pick registration / Monitoring / CLV / Dashboard
```

## 3. Šta dolazi iz API-ja

### 3.1 Fixture podaci

API može da dostavi:

- identifikator utakmice;
- domaći tim;
- gostujući tim;
- takmičenje;
- vreme početka utakmice;
- status utakmice;
- provider-specific dodatne podatke.

**Mesto u sistemu:** provider adapter i canonical `Fixture` model.  
**Timestamp:** vreme početka utakmice je poslovni podatak; vreme prijema odgovora mora se čuvati u ingestion/observability sloju kada se implementira.  
**Upotreba:** fixture discovery, universe filter, monitoring lifecycle i određivanje trenutka kada se pre-match praćenje zaustavlja.

### 3.2 Quote podaci

API može da dostavi:

- bookmaker identitet;
- bookmaker naziv;
- market;
- selection;
- odd;
- provider-specific identifikatore;
- vreme koje provider navodi, ako postoji.

**Mesto u sistemu:** provider adapter → canonical `CanonicalQuote` → istorijski `QuoteSnapshot`.  
**Timestamp-i:**

- `observed_at` — vreme na koje se podatak odnosi, ako ga provider pouzdano dostavi;
- `captured_at` — vreme kada je QuantBet primio i prihvatio podatak;
- `source` — izvor podatka.

Ako provider ne daje pouzdan timestamp, QuantBet mora koristiti sopstveni `captured_at` i jasno označiti da vreme nije provider-observation vreme.

## 4. Canonical sloj

Provider payload se ne čuva direktno u quant sloju.

Canonical modeli predstavljaju normalizovane podatke:

- `Fixture` predstavlja utakmicu;
- `CanonicalQuote` predstavlja normalizovanu kvotu;
- `ValuePick` predstavlja izračunatu procenu modela i tržišta;
- `PickRegistration` predstavlja nepromenljiv zapis registrovanog picka.

Canonical sloj mora čuvati dovoljno informacija da se zna:

- koji je fixture u pitanju;
- koji bookmaker i market su korišćeni;
- koja je vrednost kvote;
- kada je podatak posmatran ili uhvaćen;
- iz kog izvora je došao.

## 5. Istorijsko čuvanje kvota

Jedna kombinacija `fixture + bookmaker + market + selection` predstavlja **quote series**.

Jedna quote series ima više snapshot-a kroz vreme.

```text
QuoteSeries
    ├── Snapshot 1 — first seen
    ├── Snapshot 2 — promena kvote
    ├── Snapshot 3 — entry quote
    ├── Snapshot 4 — kasnija pre-match promena
    └── Snapshot N — closing quote
```

Svaki snapshot mora imati najmanje:

- stabilni identitet quote series;
- snapshot identitet;
- odd;
- `observed_at`, kada je poznat;
- `captured_at`;
- source;
- referencu na fixture;
- informaciju da li je podatak validan za pre-match fazu.

Snapshot se ne prepravlja naknadno. Nova informacija se upisuje kao novi snapshot.

## 6. Ključni momenti u životnom ciklusu

### 6.1 Fixture discovery

Sistem pronalazi buduće utakmice.

Čuva se:

- fixture identitet;
- osnovni podaci o utakmici;
- kickoff vreme;
- vreme kada je fixture otkriven ili osvežen;
- provider/source informacija.

### 6.2 Prvo hvatanje kvote

Kada se prvi put vidi validna kvota za određenu quote series:

- upisuje se prvi `QuoteSnapshot`;
- snapshot dobija `captured_at`;
- taj snapshot postaje kandidat za `first_seen` referencu.

### 6.3 Evaluacija value pick-a

Kada se model probability uporedi sa kvotom:

- čuva se model probability;
- implied probability;
- probability gap;
- expected value;
- model/configuration verzija;
- vreme izračunavanja;
- referenca na quote snapshot korišćen u izračunavanju.

### 6.4 Registracija pick-a

Kada se pick objavi ili registruje:

- kreira se immutable `PickRegistration`;
- čuva se `registered_at`;
- čuva se entry quote snapshot referenca;
- čuva se entry odd;
- čuva se kompletan decision context;
- kasnije promene kvote ne menjaju registrovani pick.

### 6.5 Background monitoring

Monitoring worker periodično prikuplja nove pre-match kvote.

Za svaki validan podatak:

- beleži se novi snapshot;
- čuva se timestamp prijema;
- čuva se source;
- povezuje se snapshot sa quote series;
- proverava se da li je kickoff već prošao;
- podatak nakon kickoff-a ne sme biti označen kao validan pre-match snapshot.

Monitoring mora raditi nezavisno od toga da li je dashboard otvoren.

### 6.6 Closing quote

Closing quote je poslednji validan pre-match snapshot prihvaćen pre stvarnog kickoff vremena.

Mora se znati:

- koji snapshot je izabran;
- kada je uhvaćen;
- koja je bila kvota;
- zašto je prihvaćen kao closing reference.

Slučajan poslednji zapis nije automatski validan closing quote.

### 6.7 CLV

CLV koristi najmanje:

- nepromenljivu entry kvotu;
- validnu closing kvotu;
- timestamp entry snapshot-a;
- timestamp closing snapshot-a;
- definisanu CLV metodologiju i verziju.

CLV se ne računa samo na osnovu trenutne kvote ili proizvoljnog snapshot-a.

## 7. Šta se trenutno ne čuva ili još nije implementirano

Trenutno nisu potvrđeni kao production-persisted:

- istorijski quote series i quote snapshot model;
- trajni PickRegistration repository;
- trajni ValuePick zapis;
- CLV zapis;
- monitoring worker state;
- dashboard read model;
- API response receipt log sa potpunim timestamp-ima;
- PostgreSQL production storage.

Ovaj dokument opisuje ciljnu organizaciju podataka, a ne tvrdi da su sve navedene funkcije već implementirane.

## 8. Dokumentaciona mapa

| Informacija | Primarni dokument |
|---|---|
| Canonical quote pravila | `docs/PERSISTENCE_BOUNDARY.md` |
| Quote application use case | `docs/QUOTE_USE_CASES.md` |
| SQLite trenutno stanje | `docs/SQLITE_PERSISTENCE.md` |
| PostgreSQL pravac | `docs/POSTGRESQL_PERSISTENCE_PLAN.md` |
| Historical pre-match quote dizajn | `docs/HISTORICAL_PREMATCH_QUOTES_DESIGN.md` |
| Pick registration domen | `docs/PICK_REGISTRATION.md` |
| Product lifecycle i faze | `docs/QUANTBET_EXECUTION_PLAN.md` |
| Velike završene celine | `docs/PROGRESS.md` |
| Detaljni zapisi iteracija | `docs/ITERATION_LOG.md` |

## 9. Pravilo za buduće izmene

Svaka nova informacija ili novi izvor mora pre implementacije dobiti:

- naziv informacije;
- izvor;
- canonical model ili DTO;
- mesto čuvanja;
- timestamp pravilo;
- lifecycle trenutak nastanka;
- pravilo izmene ili zabranu izmene;
- dokument u kome je objašnjena.

Tek nakon toga može se dodati runtime implementacija.
