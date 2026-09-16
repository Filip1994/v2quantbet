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
- Implementirani su PostgreSQL quote-history repository, migration runner, application composition i production worker entrypoint.

> Ovo potvrđuje ciljnu infrastrukturu i repository/runtime putanju, ne live Railway deployment, backup/DR ili operativni pilot.

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

## G — Fixture identity i API-Football granice

- API-Football fixture discovery čuva canonical identitet `api-football:<id>` i odvojeni pozitivni numeric provider ID za transport.
- Discovered fixture čuva authoritative, ordered provider home/away team IDs u `api-football` namespace-u.
- Odds ingestion proverava response fixture identity pre flattening-a i odbija missing, wrong, malformed ili contradictory provider identity.
- Canonical quotes koriste isti canonical fixture identity; raw numeric provider ID nije quote/business identity.

## H — Fixture-bound prediction i value foundation

- `DixonColesModel` zahteva eksplicitni `team_id_namespace`; namespace je compatibility claim, ne dokaz porekla training podataka.
- `DixonColesFixturePredictor` izvodi kontrolisani target iz authoritative `Fixture`, čuva home/away redosled i odbija namespace mismatch i jednake team IDs.
- `FixturePrediction` je vezan za target, a valuation zahteva exact canonical fixture equality pre probability/value mapiranja.
- Implementirani su canonical market/selection probability mapping i osnovni value izračun.

## Trenutna granica

Do sada je izgrađen i testiran quant/domain foundation, API-Football fixture/odds identity path, PostgreSQL quote-history path, discovery-driven worker i fixture-bound prediction/value foundation. Production completed-match acquisition i verified training provenance još ne postoje; zato production fixture-to-model execution, eligibility policy, Daily Bulletin, pick monitoring, closing/CLV, API/dashboard i operational pilot nisu završeni kao end-to-end sistem.
