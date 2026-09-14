# QuantBet — Iteration Log

Ovaj dokument beleži manje korake rada na projektu, uključujući read-only preglede, analize, odluke, implementacije, testove, CI provere i dokumentacione izmene.

## Pravila vođenja

- Svaka radna iteracija dobija zaseban unos.
- Unos se piše ljudski čitljivim jezikom.
- Navodi se šta je provereno ili urađeno, bez predstavljanja planiranog rada kao završenog.
- Za implementacione iteracije beleže se izmenjeni fajlovi, testovi, CI rezultat i commit kada su dostupni.
- Svaki unos sadrži timestamp u ISO 8601 formatu.
- `docs/PROGRESS.md` ostaje sažeti pregled većih završenih celina; ovaj dokument čuva detalje manjih koraka.

## 2026-09-14T00:00:00Z — Uведен дневник iteracija

- Pregledan je postojeći `docs/PROGRESS.md`.
- Dogovoreno je da se velike završene celine i dalje evidentiraju u `docs/PROGRESS.md`.
- Za manje korake uvodi se ovaj detaljni dnevnik.
- Od sada će se posle svake relevantne iteracije beležiti šta je provereno, šta je promenjeno i kakav je rezultat provere.
- Ova izmena je dokumentaciona i ne menja runtime ponašanje sistema.

## 2026-09-14T00:00:00Z — Dizajn istorijskih pre-match quote snapshot-a

- Read-only pregledani su `docs/QUOTE_USE_CASES.md`, `docs/PICK_REGISTRATION.md`, `docs/PERSISTENCE_BOUNDARY.md` i `docs/QUANTBET_EXECUTION_PLAN.md`.
- Potvrđeno je da postojeći identitet quote-a omogućava samo jednu vrednost po market/selection kombinaciji i nije dovoljan za istoriju snapshot-a.
- Dodat je novi dizajn dokument `docs/HISTORICAL_PREMATCH_QUOTES_DESIGN.md`.
- Dokument definiše quote series, immutable quote snapshots, eksplicitnu entry snapshot referencu, first-seen/current/closing pre-match checkpoint-e, kickoff granicu, monitoring boundary i CLV-ready podatke.
- Live/in-play kvote su eksplicitno izvan obuhvata.
- Nije menjano runtime ponašanje, nisu menjani modeli, repository interfejsi niti PostgreSQL šema.
- Commit: `0c49185495acf8779424e71583442e5cd1379fe9d`.
- CI rezultat: nije proveravan u ovoj iteraciji.

## 2026-09-14T14:43:00+02:00 — Uvedena mapa podataka i timestamp pravila

- Dodat je `docs/DATA_CLARIFICATION.md` kao centralna mapa podataka projekta.
- Dokument jednostavnim jezikom objašnjava šta QuantBet prima iz API-ja, kroz koje slojeve prolazi, gde se čuva i u kom trenutku nastaje.
- Posebno su objašnjeni fixture podaci, quote podaci, canonical modeli, istorijski snapshot-i, pick registracija, background monitoring, closing quote i CLV.
- Dodat je pregled informacija koje još nisu production-persisted.
- Dodat je indeks koji povezuje vrste podataka sa odgovarajućim `.md` dokumentima.
- Uvedeno je pravilo da svaka buduća informacija pre implementacije mora imati definisan izvor, model, mesto čuvanja, timestamp pravilo i lifecycle trenutak.
- Runtime kod nije menjan.
- Testovi i CI nisu pokretani.
- Commit dokumenta: `f50a46051bded75886050cb3005afcc9dd1931c7`.

## 2026-09-14T14:43:00+02:00 — Implementirani osnovni istorijski quote domen modeli

- Dodat je `src/h2h/domain/quote_history.py`.
- Uvedeni su immutable modeli `QuoteSeries` i `QuoteSnapshot`.
- `QuoteSeries` čuva stabilni identitet fixture/bookmaker/market/selection kombinacije.
- `QuoteSnapshot` čuva jednu nepromenljivu opservaciju sa `observed_at`, `captured_at`, kvotom i izvorom.
- Uvedena je validacija obaveznih identifikatora, kvote i timezone-aware timestamp-a.
- Dodat je `tests/domain/test_quote_history.py` sa testovima za validaciju i immutability.
- Pokušaj ažурирања `src/h2h/domain/__init__.py` није успео због SHA mismatch-а; export modela još nije završen.
- CI nije proveravan u ovoj iteraciji.
- Commit modela: `c0c52785afd82f1502800b500dc04f3a92f638f1`.
- Commit testova: `013d384d8543888e11ab12eacd6f38518d4d9726`.

## 2026-09-14T14:43:00+02:00 — Završen export quote history modela

- Ažuriran je `src/h2h/domain/__init__.py`.
- `QuoteSeries` i `QuoteSnapshot` sada su dostupni i kroz centralni `h2h.domain` import.
- Prethodni SHA mismatch je rešen korišćenjem aktuelnog sadržaja fajla.
- Runtime logika modela nije menjana; promenjen je samo javni domen export.
- Testovi i CI nisu pokretani u ovoj iteraciji.
- Commit: `7ec565d2a3909dc25373c8a6ea27e8970cc40071`.

## 2026-09-14T14:43:00+02:00 — Dodati testovi za quote history repository

- Dodat je `tests/persistence/test_quote_history.py`.
- Pokrivena je idempotentnost `ensure_series` operacije.
- Pokriveno je odbijanje konflikta pri ponovnoj upotrebi `series_id`.
- Pokriveno je čuvanje istorije snapshot-a i redosled upisa.
- Pokrivena je idempotentnost `append_snapshots` operacije.
- Pokrivena je atomicnost pri konfliktu snapshot ID-ja.
- Testovi i CI još nisu provereni.
- Commit testova: `b79241889f80a469a0c803dd11826c0f2d57f236`.

## 2026-09-14T15:00:00+02:00 — Ojačan ugovor quote history repository-ja

- `QuoteHistoryRepository` sada eksplicitno izlaže `series_for_fixture`.
- Snapshot može biti upisan samo ako prethodno postoji odgovarajući `QuoteSeries`.
- Dodata je zaštita od upisa snapshot-a sa nepoznatim `series_id`.
- Očuvana je atomicnost batch upisa: nijedan snapshot se ne upisuje ako batch sadrži konflikt ili nepoznatu seriju.
- Testovi su usklađeni sa novim ugovorom i prošireni proverom nepoznate serije i pretrage serija po fixture-u.
- Izmenjeni fajlovi: `src/h2h/persistence/quote_history.py`, `tests/persistence/test_quote_history.py`.
- Testovi i CI nisu izvršeni u ovom okruženju.
- Commit implementacije: `0c5b230d8b254723f140f5149a4576529fd7ed7e`.
- Commit testova: `afb04a114ac8915c7304f51837ceadb7b5be9757`.

## 2026-09-14T15:15:00+02:00 — Dodat PostgreSQL schema migration za quote history

- Dodat je `migrations/001_quote_history.sql` za Railway PostgreSQL.
- Definisane su tabele `quote_series` i `quote_snapshots`.
- `quote_series` ima stabilan `series_id`, fixture/bookmaker/market/selection identitet, vremensku oznaku kreiranja i jedinstveno ograničenje po seriji.
- `quote_snapshots` je append-only tabela sa FK vezom ka seriji, validacijom kvote, timestamp kolonama i zaštitom od dupliranja identične opservacije.
- Dodati su indeksi za pretragu serija po fixture-u i snapshot-a po seriji/vremenu.
- PostgreSQL adapter, runtime povezivanje, migracioni runner, integracioni testovi i CI provera još nisu implementirani.
- Testovi i CI nisu izvršeni u ovom okruženju.
- Commit: `dc461bf76896ffcbff0d4c1b3869b3018e14db11`.

## 2026-09-14T18:45:00Z — Proširena PostgreSQL quote-history test pokrivenost

- Provereno je da migration runner validira postojanje migration direktorijuma i odbija fajl prosleđen umesto direktorijuma.
- Prošireni su testovi za `PostgreSQLQuoteHistoryRepository`.
- Pokriven je upis nove `QuoteSeries` instance.
- Pokriven je konflikt postojeće serije sa istim `series_id`.
- Pokriveno je odbijanje snapshot-a za nepoznatu seriju.
- Pokriven je upis snapshot-a, idempotentni ponovni upis i konflikt snapshot-a sa istim ID-em.
- Testovi koriste injektovanu connection factory funkciju, bez zahteva za aktivnim PostgreSQL serverom.
- Izmenjeni fajl: `tests/persistence/test_postgres_quote_history.py`.
- CI rezultat nije potvrđen; GitHub Actions za poslednji commit nije vratio workflow run.
- Commit testova: `31d5729de9ebdd3e5adfc72d308cdf45ade9477e`.
- Commit dodatne idempotency/conflict pokrivenosti: `85b52ad11deeac0ab2e0c0c99238d52df4be2118`.

## 2026-09-14T16:20:00-04:00 — Prošireni PostgreSQL read-path testovi

- Ažuriran je `tests/persistence/test_postgres_quote_history.py`.
- Fake connection sloj sada čuva redove u obliku koji odgovara SQL adapteru, umesto da meša primarne ključeve sa payload kolonama.
- Dodati su testovi za `series_for_fixture`, `snapshots_for_series` i `get_snapshot`.
- Zadržani su postojeći testovi za upis, idempotentnost i detekciju konflikata.
- Runtime PostgreSQL adapter nije menjan.
- Lokalno izvršavanje testova i CI nisu potvrđeni u ovom okruženju.
- Commit: `bf3d62b7cf6f60a90b331cfd6e7d678a9ca69a54`.
