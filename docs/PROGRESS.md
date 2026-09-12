# QuantBet — Progress Log

Ovaj dokument beleži usvojene odluke, izvršene korake i sledeći mali implementacioni zadatak. Ne predstavlja tvrdnju da je ceo roadmap završen.

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

Podržavamo samo:

- `OU_25` — ukupno golova 2.5;
- `BTTS` — oba tima daju gol.

Za `OU_25` selekcije su `OVER` i `UNDER`.
Za `BTTS` selekcije su `YES` i `NO`.

Ne uvodimo dodatna tržišta bez nove eksplicitne odluke.

### 5. Kanonski model — usvojeni smer

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
- Ne širiti scope tržišta bez eksplicitnog dogovora.
- Ne prosleđivati provider-specific odds strukture direktno u quant sloj.
- Ne mešati immutable observations sa lifecycle ulogama i izvedenim metrikama.
- Ne raditi široke refaktore; implementirati jednu malu celinu uz testove.

## Sledeći korak

Precizirati i implementirati kanonski quote/odds-snapshot contract, počevši od:

1. jasnih tipova za `market` i `selection`;
2. validacionih pravila za `odd` i `opposite_odd`;
3. immutable observation zapisa;
4. testova za validne i nevalidne kombinacije.

Tek nakon toga povezivati provider normalizaciju, persistence i lifecycle checkpoint-e.
