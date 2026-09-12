# QuantBet — Progress Log

Ovaj dokument beleži usvojene odluke, izvršene korake i sledeći mali implementacioni zadatak. Ne predstavlja tvrdnju da je ceo roadmap završen.

## Poslednje ažuriranje

- Datum i vreme: **2026-09-13**
- Ažurirano: C5.8 normalizator je implementiran kao mali provider-neutral sloj; dodati su testovi, a domen i dalje ostaje završna validaciona granica.

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

### 7. Validacioni sloj — C5.7

- Dodat je `validate_quotes()` u `src/h2h/domain/quote_validation.py`.
- Validator zahteva nepraznu kolekciju isključivo `CanonicalQuote` objekata.
- Proverava tačno kompletan skup selekcija za podržano tržište i zajednički fixture, bookmaker, market i timestamp.
- `MarketSnapshot` koristi validator pre daljih provera konteksta.
- Dodati su testovi za validnu kolekciju, praznu kolekciju, mešani fixture i nevalidne tipove.
- CI run #93 i #94 su završeni sa statusom `success`.
- CI run #89 je bio neuspešan zbog neispravne tvrdnje o duplicate identity testu; test je uklonjen jer `selection` jeste deo identity-ja.

### 8. Normalizacija quote-a — C5.8

- Dodat je `normalize_quote()` u `src/h2h/domain/quote_normalizer.py`.
- Uveden je `QuoteNormalizationError` za neuspešnu normalizaciju.
- Provider-neutral ulaz je mapiran na postojeće `Market` i `Selection` vrednosti.
- Podržani marketi ostaju samo `OU_25` i `BTTS`; podržan je i eksplicitni alias `TOTALS_2_5` za `OU_25`.
- Svaki izlaz se konstruiše kao `CanonicalQuote`, pa postojeća domen-validacija ostaje konačna zaštitna granica.
- Dodati su testovi za validne market/selection kombinacije, alias, nepoznat market, nepoznatu selekciju, nedostajuće polje, nevalidnu kvotu i pogrešan tip ulaza.

## Važne odluke

- Ne koristiti `peak_quote`.
- Ne širiti aktivni scope tržišta bez eksplicitnog dogovora.
- Ne prosleđivati provider-specific odds strukture direktno u quant sloj.
- Ne mešati immutable observations sa lifecycle ulogama i izvedenim metrikama.
- Ne raditi široke refaktore; implementirati jednu malu celinu uz testove.
- Normalizator ostaje provider-neutral dok ne uvedemo konkretan adapter.
- Sve buduće izmene ovog dokumenta moraju imati datum i vreme.

## Sledeći korak

Proveriti CI za C5.8 i, ako je zelen, napraviti sledeći mali ugovor za formiranje `MarketSnapshot` iz normalizovanih `CanonicalQuote` observacija. Provider adaptere, persistence, workere, lifecycle checkpoint-e i CLV ostaviti za odvojene korake.
