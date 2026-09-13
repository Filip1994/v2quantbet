# QuantBet — Completed Work

Ovaj dokument sadrži samo proverene, do sada završene radove. Ne predstavlja tvrdnju da je ceo sistem production-ready.

## A — Osnovna struktura i alati

- Postavljen je kanonski repozitorijum `Filip1994/v2quantbet`.
- Postavljena je osnovna `src`/`tests` struktura.
- Uvedeni su razvojni alati, minimalni test setup i standardna lokalna provera kvaliteta (`ruff` i `pytest`).
- Python je lokalno fiksiran na 3.11.
- Dodat je i zaključan dependency fajl `uv.lock`.

## B — Konfiguracija i PostgreSQL infrastruktura

- Implementiran je i testiran minimalni konfiguracioni ugovor.
- Konfiguraciona reprezentacija rediguje database/API tajne.
- Verifikovana je Railway PostgreSQL infrastruktura, uključujući servis, repliku i persistent volume.
- Identifikovane su i uklonjene legacy aplikacione tabele.
- Verifikovani su read readiness preko `SELECT 1`, identitet baze `railway` / `postgres` i odsustvo aplikacionih tabela u `public` šemi.

> Infrastruktura je proverena, ali aplikacioni persistence sloj još nije implementiran kao celina.

## C — Quant baseline i stabilizacija

- Dixon–Coles model je prenet u V2.
- Zabeležen je legacy quant referentni commit i dodati regression anchor-i u `docs/quant-golden-master.md`.
- Dodat je deterministički, izvršivi golden-master fixture/test.
- Usklađena je zaključana referenca za `rho` sa legacy numeričkim baseline-om.
- Dodati su testovi za boundary uslove, edge cases, numeričku stabilnost, market invariants i determinism.
- Javna quant API izloženost i behavior contract su provereni i testirani.
- Quant namespace je konsolidovan na kanonski `h2h`; uklonjeni su duplirani `quantbet` domain namespace fajlovi.
- Quant matematika je zaštićena golden-master testovima.

## D — Canonical odds/domain sloj

- Uveden je immutable `CanonicalQuote` za jednu kvotu konkretne selekcije.
- Definisani su identitet i validacija quote-a: fixture, bookmaker, market, selection, odd, observed timestamp i source.
- Uveden je `MarketSnapshot` za kompletan snapshot jednog fixture/bookmaker/market/timestamp konteksta.
- Definisani su market invariants: `OU_25` mora sadržati `OVER` i `UNDER`, a `BTTS` mora sadržati `YES` i `NO`.
- `opposite_odd` nije dodat u osnovni quote zapis; suprotna kvota se dobija iz druge quote-observacije u snapshot-u.
- Lifecycle checkpoint-i su definisani kao uloge nad immutable istorijom, a ne kao četiri duplirana osnovna zapisa.
- Uveden je centralni `validate_quotes()` validator.
- Dodati su testovi za validne i nevalidne kolekcije, prazne ulaze, mešane fixture-e, nevalidne tipove i market invariants.

## E — Quote normalizacija

- Dodat je provider-neutral `normalize_quote()` sloj.
- Uveden je `QuoteNormalizationError`.
- Provider-neutral ulaz se mapira na postojeće `Market` i `Selection` vrednosti.
- Aktivni scope ostaje `OU_25` (`OVER`, `UNDER`) i `BTTS` (`YES`, `NO`).
- Podržan je alias `TOTALS_2_5` za `OU_25`.
- Svaki izlaz konstruiše se kao `CanonicalQuote`, tako da domen-validacija ostaje konačna zaštitna granica.
- Dodati su testovi za validne kombinacije, alias, nepoznat market/selekciju, nedostajuća polja, nevalidne kvote i pogrešne tipove ulaza.

## F — CI i usvojene odluke

- CI je verifikovan kao zelen nakon quant/domain izmena.
- Dependency set je ostao minimalan.
- Nisu dodati API ključevi niti drugi secret-i u Git.
- Usvojeno je pravilo: jedna mala celina po koraku, testovi pre prelaska dalje, bez provider-specific struktura u quant sloju, bez širokih refaktora bez razloga i bez širenja market scope-a bez eksplicitne odluke.
- `peak_quote` koncept se ne koristi.

## Trenutna granica

Do sada je izgrađen i testiran quant/domain foundation, uključujući canonical quote validaciju i provider-neutral normalizaciju. Production ingestion, persistence, fixture lifecycle, decision/risk, pick lifecycle, CLV, bulletin, API/dashboard i operativni monitoring još nisu završeni kao end-to-end sistem.
