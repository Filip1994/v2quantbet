# QuantBet — Progress Log

Ovaj dokument beleži usvojene odluke, izvršene korake i sledeći mali implementacioni zadatak. Ne predstavlja tvrdnju da je ceo roadmap završen.

## Poslednje ažuriranje

- Datum i vreme: **2026-09-12 14:53:49 CEST (UTC+02:00)**
- Ažurirano: scope tržišta i naredni implementacioni korak.

## Trenutno stanje

- Rad se vodi na repozitorijumu `Filip1994/v2quantbet`, grana `main`.
- V2 je trenutno arhitektonski i quant baseline; produkcioni ingestion, persistence i lifecycle slojevi još nisu implementirani kao celina.
- Legacy `Filip1994/h2h` koristi se samo kao referentni materijal, ne kao arhitektonski šablon.

## Šta je urađeno

### 1. Quant baseline

- Dixon–Coles model je prenet u V2.
- Matematička logika je proverena prema legacy implementaciji.
- Dodat je golden-master regression test.
- Baseline je zaključan testovima i verzijama NumPy/SciPy.

### 2. Product ciljevi i CLV semantika

- Dokumentovani su ciljevi sistema u `docs/QUANTBET_GOALS.md`.
- Razdvojeni su:
  - value;
  - expected CLV;
  - realized CLV.
- Definisano je da se realized CLV računa naknadno, uz validnu closing referencu.
- Definisani su obavezni odds checkpoint-i:
  - `first_seen_quote`;
  - `pick_quote`;
  - `current_quote`;
  - `closing_quote`.

### 3. Arhitektura

- U `docs/architecture.md` dokumentovan je planirani tok:

  `Provider -> Raw Odds -> Normalizer -> Canonical Quote -> Validation -> Market Snapshot -> Quant -> Decision -> Risk -> Bet lifecycle -> Settlement`

- Ispravljena je terminologija: `peak_quote` je uklonjen i zamenjen sa `pick_quote`.
- `pick_quote` znači validnu kvotu u trenutku objave tipa/biltena i predstavlja referentnu ponuđenu cenu za pick.

### 4. Scope tržišta

Za sada ostajemo striktno na dva tržišta:

- `OU_25` — ukupno golova 2.5;
- `BTTS` — oba tima daju gol.

Za `OU_25` selekcije su `OVER` i `UNDER`.
Za `BTTS` selekcije su `YES` i `NO`.

Dodatna tržišta nisu deo trenutne implementacije.

### 5. Plan proširenja tržišta — nije aktivni scope

Ovo je samo zabeležen budući plan, bez implementacije:

1. **Faza A — sada:** `OU_25` i `BTTS`.
2. **Faza B — nakon stabilizacije osnovnog ugovora i podataka:** `OU_15` i `OU_35`.
3. **Faza C — nakon provere modela za tri ishoda:** `MATCH_RESULT` sa selekcijama `HOME`, `DRAW`, `AWAY`.
4. Asian Handicap, corners, cards, player props i slična tržišta ostaju van plana dok ne postoji poseban model i dovoljan kvalitet podataka.

Ovaj plan ne menja trenutni scope. Svako aktiviranje nove faze zahteva novu eksplicitnu odluku.

### 6. Kanonski model — usvojeni smer

Kanonski zapis treba da razlikuje tržište od selekcije:

- `market`: `OU_25` ili `BTTS`;
- `selection`: `OVER`, `UNDER`, `YES` ili `NO`, u zavisnosti od tržišta;
- `odd`: kvota izabrane selekcije;
- `opposite_odd`: kvota suprotne selekcije;
- identifikator utakmice i kladionice;
- vreme opažanja;
- izvor/provenance.

`first_seen_quote`, `pick_quote`, `current_quote` i `closing_quote` nisu četiri različita tipa osnovnog podatka. Oni su lifecycle uloge nad istorijom immutable quote-observacija.

## Važne odluke

- Ne koristiti `peak_quote`.
- Ne širiti aktivni scope tržišta bez eksplicitnog dogovora.
- Ne prosleđivati provider-specific odds strukture direktno u quant sloj.
- Ne mešati immutable observations sa lifecycle ulogama i izvedenim metrikama.
- Ne raditi široke refaktore; implementirati jednu malu celinu uz testove.
- Sve buduće izmene ovog dokumenta moraju imati datum i vreme.

## Sledeći korak

Pre implementacije treba potvrditi minimalni tehnički oblik kanonskog ugovora:

1. neutralni package path, bez korišćenja `src/h2h/domain` kao novog kanonskog domena;
2. jasni tipovi za `market` i `selection`;
3. da li `opposite_odd` ostaje deo osnovnog zapisa ili postaje izvedena vrednost za binarna tržišta;
4. immutable observation zapis;
5. testovi za validne i nevalidne kombinacije.

Nakon potvrde tog minimalnog ugovora implementirati samo `CanonicalQuote` i njegove testove. Provider normalizaciju, persistence, worker-e, lifecycle checkpoint-e i CLV ostaviti za sledeće odvojene korake.
