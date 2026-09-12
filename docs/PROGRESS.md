# QuantBet — Progress Log

Ovaj dokument beleži usvojene odluke, izvršene korake i sledeći mali implementacioni zadatak. Ne predstavlja tvrdnju da je ceo roadmap završen.

## Poslednje ažuriranje

- Datum i vreme: **2026-09-12 15:00:00 CEST (UTC+02:00)**
- Ažurirano: implementirani `CanonicalQuote` i `MarketSnapshot` ugovori sa osnovnim testovima.

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
- Razdvojeni su value, expected CLV i realized CLV.
- Realized CLV se računa naknadno, uz validnu closing referencu.
- Definisani su odds checkpoint-i: `first_seen_quote`, `pick_quote`, `current_quote` i `closing_quote`.

### 3. Arhitektura

- Planirani tok je:

  `Provider -> Raw Odds -> Normalizer -> Canonical Quote -> Validation -> Market Snapshot -> Quant -> Decision -> Risk -> Bet lifecycle -> Settlement`

- `pick_quote` znači validnu kvotu u trenutku objave tipa/biltena i predstavlja referentnu ponuđenu cenu za pick.

### 4. Scope tržišta

Za sada ostajemo striktno na dva tržišta:

- `OU_25` — ukupno golova 2.5, selekcije `OVER` i `UNDER`;
- `BTTS` — oba tima daju gol, selekcije `YES` i `NO`.

Dodatna tržišta nisu deo trenutne implementacije.

### 5. Plan proširenja tržišta — nije aktivni scope

1. Faza A — sada: `OU_25` i `BTTS`.
2. Faza B — nakon stabilizacije osnovnog ugovora i podataka: `OU_15` i `OU_35`.
3. Faza C — nakon provere modela za tri ishoda: `MATCH_RESULT` sa selekcijama `HOME`, `DRAW`, `AWAY`.
4. Asian Handicap, corners, cards, player props i slična tržišta ostaju van plana dok ne postoji poseban model i dovoljan kvalitet podataka.

Svako aktiviranje nove faze zahteva novu eksplicitnu odluku.

### 6. Kanonski modeli

- `CanonicalQuote` je immutable zapis jedne kvote konkretne selekcije.
- Sadrži identifikator utakmice i kladionice, tržište, selekciju, kvotu, vreme opažanja i izvor.
- `MarketSnapshot` predstavlja kompletan binarni snapshot za jedan fixture, bookmaker, market i timestamp.
- Za `OU_25` snapshot mora sadržati tačno `OVER` i `UNDER`.
- Za `BTTS` snapshot mora sadržati tačno `YES` i `NO`.
- `opposite_odd` nije deo osnovnog `CanonicalQuote` zapisa; suprotna kvota se dobija iz odgovarajuće druge quote-observacije u snapshot-u.
- Lifecycle checkpoint-i su uloge nad istorijom immutable quote-observacija, a ne četiri različita osnovna zapisa.

## Važne odluke

- Ne koristiti `peak_quote`.
- Ne širiti aktivni scope tržišta bez eksplicitnog dogovora.
- Ne prosleđivati provider-specific odds strukture direktno u quant sloj.
- Ne mešati immutable observations sa lifecycle ulogama i izvedenim metrikama.
- Ne raditi široke refaktore; implementirati jednu malu celinu uz testove.
- Sve buduće izmene ovog dokumenta moraju imati datum i vreme.

## Sledeći korak

Definisati sledeći mali ugovor: validacioni sloj koji će proveravati ulazne `CanonicalQuote` zapise pre formiranja `MarketSnapshot` objekta. Provider normalizaciju, persistence, worker-e, lifecycle checkpoint-e i CLV ostaviti za odvojene korake.
