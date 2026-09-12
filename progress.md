# Progress Log

> Hronološki zapis promena, validacije i sledećih koraka.

## 2026-09-12

### A1–A4.2 — Osnovna struktura i konfiguracija
- Potvrđen kanonski repozitorijum `Filip1994/v2quantbet`.
- Postavljeni osnovna struktura projekta, razvojni alati, minimalni test setup i lokalna provera kvaliteta.
- Python verzija lokalno fiksirana na 3.11.
- Dodat i zaključan dependency fajl `uv.lock`.
- Implementiran i testiran minimalni konfiguracioni ugovor.
- Konfiguraciona reprezentacija rediguje database/API tajne.

### B1–B3.4 — Railway PostgreSQL
- Verifikovana Railway PostgreSQL produkciona infrastruktura.
- Identifikovane i uklonjene legacy aplikacione tabele.
- Verifikovani read readiness (`SELECT 1`) i identitet baze (`railway` / `postgres`).
- Potvrđeno da u `public` šemi nema aplikacionih tabela.
- Verifikovani Railway servis, replika i persistent volume.

### C1 — Quant baseline
- Zabeležen legacy quant referentni commit.
- Dodati regression anchor-i u `docs/quant-golden-master.md`.
- Quant matematika je ostavljena nepromenjena do uspostavljanja izvršivog golden-master testa.

### C2 — Izvršivi golden master
- Dodat deterministički sintetički fixture za Dixon–Coles regresiju.
- Dodat izvršivi golden-master test za ključne rezultate quant modela.
- Usklađena zaključana referenca za `rho` sa legacy numeričkim baseline-om.
- Validacija: CI je prošao; Ruff i svi testovi su bili zeleni.

### Quant namespace consolidation
- `h2h` je izabran kao kanonski namespace.
- Domain moduli za canonical odds i market snapshot premešteni u `h2h.domain`.
- Testovi domena ažurirani da koriste kanonski `h2h` namespace.
- Uklonjeni duplirani `quantbet` domain namespace fajlovi.
- Validacija: CI za poslednji dokumentacioni commit je uspešno završen.

### Dokumentacija napretka
- Dodat ovaj `progress.md` kao obavezni dnevnik promena.
- Prethodni rad je retroaktivno evidentiran na osnovu `PROJECT_STATUS.md`, `docs/quant-golden-master.md` i istorije commit-ova.

## Sledeće

- C3 — quant boundary, edge-case i numerical-stability testovi.
- Svaka naredna promena mora biti evidentirana u ovom fajlu pre proglašenja zadatka završenim.
