# QuantBet — Iteration Log

Ovaj dokument beleži manje korake rada na projektu, uključujući read-only preglede, analize, odluke, implementacije, testove, CI provere i dokumentacione izmene.

## Pravila vođenja

- Svaka radna iteracija dobija zaseban unos.
- Unos se piše ljudski čitljivim jezikom.
- Navodi se šta je provereno ili urađeno, bez predstavljanja planiranog rada kao završenog.
- Za implementacione iteracije beleže se izmenjeni fajlovi, testovi, CI rezultat i commit kada su dostupni.
- Svaki unos sadrži timestamp u ISO 8601 formatu.
- `docs/PROGRESS.md` ostaje sažeti pregled većih završenih celina; ovaj dokument čuva detalje manjih koraka.

## 2026-09-15T00:00:00+02:00 — Дод PostgreSQL startup migration hook

- Ажуриран је `src/h2h/application_postgres.py`.
- PostgreSQL application composition сада има `migrate()` метод који користи постојећи migration runner и подразумевани `migrations/` директоријум.
- Миграције се и даље не извршавају аутоматски у самом builder-у; позив је експлицитан да би lifecycle остао контролисан и тестирабилан.
- Променом није уведен live Railway deployment нити production worker entrypoint.
- Тестови и CI за ову измену нису потврђени у овом окружењу.
- Commit: `e8389e56dbf914c134b37c109e65e670997be227`.

## 2026-09-15T01:10:00+02:00 — Тестови PostgreSQL application lifecycle-а

- Проверен је актуелни `src/h2h/application_postgres.py` и постојећи application test pattern.
- Додат је `tests/test_application_postgres.py`.
- Покривено је креирање PostgreSQL application composition-а, прослеђивање connection-а migration runner-у, коришћење подразумеваног migration директоријума, безбедан `close()` и context-manager lifecycle.
- Тестови су додати, али нису локално покренути у овом окружењу.
- CI није проверен; не postoji potvrda o uspešnom ili neuspešnom workflow run-u za ovaj commit.
- Commit: `925da26461b80e579b64877f45a5aecd10cbe801`.

## 2026-09-15T01:35:00+02:00 — PostgreSQL URL u ApplicationSettings

- Ažuriran je `src/h2h/config.py`.
- `ApplicationSettings` sada opcionalno izlaže `database_url`, uz zadržavanje `database_path` radi kompatibilnosti sa postojećim SQLite potrošačima.
- `load_settings()` čita `DATABASE_URL` kada je prisutan i uklanja spoljašnje razmake.
- Ažuriran je `tests/test_config.py` sa proverama učitavanja URL-a i redakcije poverljivih vrednosti u `repr()` izlazu.
- PostgreSQL dependency (`psycopg`) i `uv.lock` namerno nisu menjani; lokalna `uv` regeneracija je i dalje potrebna.
- Testovi и CI нису покренути у овом окружењу.
- Commitovi: `22891b7222e3303d776c967a0ddde326d632823d`, `8c5442d08420c6c3cb621c94181f69fd024f0872`.

## 2026-09-15T02:00:00+02:00 — Eksplicitna PostgreSQL production composition putanja

- Ažuriran je `src/h2h/application.py`.
- Dodat je `build_postgres_quote_history_application_from_settings(settings)` builder.
- Builder zahteva `ApplicationSettings.database_url` i eksplicitno odbija nastavak bez `DATABASE_URL`; `database_path` se ne koristi kao fallback.
- SQLite builderi su zadržani samo kao legacy compatibility granica dok se ne uklone sve aktivne reference.
- PostgreSQL production composition koristi postojeći `application_postgres` modul i ne uvodi novi persistence sloj.
- Testovi и CI нису покrenути у овом окружењу.
- Commit: `30175fef3cb8dce261bf667b1882ebe593ecd46d`.

## 2026-09-15T03:00:00+02:00 — Документација production PostgreSQL границе

- Ажурирани су `docs/CONFIGURATION.md` и `docs/APPLICATION_COMPOSITION.md`.
- Документација сада јасно дефинише `DATABASE_URL` као обавезан за production и Railway.
- `QUANTBET_DATABASE_PATH` и SQLite composition су означени као привремени legacy/test-only слој; нису production fallback.
- Документација намерно не тврди да су dependency, локални тестови или CI већ проверени.
- Commitovi: `389b7559ab4d7fae0b7538a66413047c8153b5f8`, `2a19ef586e95e9221b38e8ce2e87fad8e3b1b07c`.

## 2026-09-15T03:20:00+02:00 — Дефинисана storage архитектура Railway deployment-а

- Додат је `docs/DATA_STORAGE_ARCHITECTURE.md`.
- Дефинисано је да је PostgreSQL једини извор истине за структуриране QuantBet пословне податке.
- QuantBet application service је compute/runtime слој; његов локални filesystem, RAM, логови и генерисани фајлови нису source of truth.
- Durable Barrel је дефинисан као секундарно file storage место за rebuildable cache, велике артефакте и export-е, уз правила за provenance и checksum када су потребни.
- Документовано је да Durable Barrel није backup PostgreSQL-а и да SQLite није део циљане production архитектуре.
- Тестови, CI, backup/restore и production worker startup нису потврђени овом документационом изменом.
- Commit: `70eed0e8458331a26644d7d843a487e8a0b9808b`.

## 2026-09-15T04:00:00+02:00 — PostgreSQL runtime dependency commit i Durable Barrel terminologija

- `pyproject.toml` i `uv.lock` sada eksplicitno sadrže PostgreSQL runtime dependency `psycopg[binary]`.
- Lokalna verifikacija nakon instalacije: `uv run pytest` → `208 passed`; `uv run ruff check .` → `All checks passed!`.
- Dependency promena je commitovana i pushovana na `main` kao `8daf196`.
- `docs/DATA_STORAGE_ARCHITECTURE.md` je ispravljen tako da koristi tačan Railway termin **Durable Barrel** umesto prethodnog pogrešnog naziva Durable Volume.
- Ova dokumentaciona korekcija je commitovana kao `16d2572`.

## 2026-09-15T05:00:00+02:00 — Коoperativно gašenje worker runtime-a

- Ažuriran je `src/h2h/workers/runtime.py`.
- Dodat je `should_stop` predicate kako bi production supervisor mogao kontrolisano da zaustavi worker pre sledeće iteracije.
- Postojeće ponašanje je zadržano: bez prosleđenog predicate-a runtime nastavlja rad kao ranije, a spoljašnji signal i dalje može prekinuti proces.
- Dodat je test koji proverava da se nakon aktiviranja stop uslova ne pokreće naredna iteracija.
- Testovi i Ruff nisu pokrenuti u ovom okruženju.
- Commitovi: `909592dfbad80ffd019af5adaafad977d0560b8f`, `aa91ada060913d6e6005d27016a757bb826a0ebe`.

## 2026-09-15T05:20:00+02:00 — Prosleđivanje shutdown predicate-a kroz javni worker API

- Ažuriran je `src/h2h/workers/runtime.py`.
- `run_worker()` sada prihvata `should_stop` i prosleđuje ga `WorkerRuntime` instanci.
- Dodat je test koji potvrđuje da se worker zaustavlja kooperativno i kroz convenience funkciju `run_worker()`.
- Lokalni `pytest` i Ruff nisu pokrenuti u ovom okruženju; CI treba da potvrdi promenu.
- Commitovi: `6c9fa851f853e87ddfa77fc20e1b66b4c38d25be`, `31c0cdb794f46d6fe59212475c03f2eacf07007`.

## 2026-09-15T06:30:00+02:00 — Изолација грешака по fixture-у у discovery worker-у

- Ажуриран је `src/h2h/workers/discovered_history_quote_polling.py`.
- Greška pri provider fetch-u ili ingestion-u sada se loguje sa traceback-om i ne prekida obradu ostalih fixture-a u istom ciklusu.
- Dodat je test `test_continues_after_fixture_failure`.
- Lokalna verifikacija za ovu izmenu još nije izvršena; potrebno je pokrenuti `uv run pytest` i `uv run ruff check .`.
- Commitovi: `134b60f5e4618839af06c1a2e0f17598aa70c5e7`, `51db83994d9efcc9903e8228965390e1734aa0c3`.

## 2026-09-15T09:00:00+02:00 — Centralni bookmaker allowlist guard

- Dodat je `src/h2h/domain/bookmaker_policy.py`.
- Uveden je centralni allowlist: `superbet`, `1xbet`, `bet365`.
- Identifikatori se normalizuju trimovanjem i `casefold()` operacijom.
- Nepoznati bookmaker-i se odbacuju kroz `UnsupportedBookmakerError`; prazne vrednosti i tipovi koji nisu string se odbacuju eksplicitno.
- Dodat je `tests/test_bookmaker_policy.py` sa proverama dozvoljenih, nedozvoljenih, praznih i ne-string identifikatora.
- Lokalni testovi, Ruff i CI nisu pokrenuti u ovom okruženju.
- Commitovi: `08005a503b34033ca153decf24cf01ae7ab237e9`, `83f20660ca4df5ef98e460a5cb0ecbac3298e069`.

## 2026-09-15T09:30:00+02:00 — Usvojena konzervativna politika quote refresh-a

- Ažuriran je `docs/architecture.md`.
- Dokumentovana je ugovorena, konzervativna frekvencija osvežavanja kvota:
  - discovery do 72 sata unapred, približno na 15 minuta;
  - T−72h do T−48h: jednom dnevno;
  - T−48h do T−24h: na 12 sati;
  - T−24h do T−6h: na 6 sati;
  - T−6h do T−2h: na 2 sata;
  - T−2h do kickoff-a: na 30 minuta;
  - T−15 minuta: posebna završna/closing captura.
- Naglašeno je da se quote refresh radi selektivno, samo za relevantne fixture-e, markete i dozvoljene bookmaker-e.
- Discovery ne sme automatski da pokreće kompletnu quote kolekciju za svaki pronađeni fixture.
- Prethodni globalni polling od 60 sekundi nije usvojena politika.
- Ovo je dokumentaciona odluka; implementacija cadence scheduler-a, testovi i CI još nisu potvrđeni.
- Commit: `de6d9caa2b01baade472c73956c3ff82b1aa5f79`.

## 2026-09-15T10:00:00+02:00 — Izolovani kickoff-aware quote refresh scheduler

- Dodat je `src/h2h/workers/quote_refresh_schedule.py`.
- Scheduler je čist, izolovan i ne menja postojeći production worker.
- Na osnovu `now` i `kickoff_at` vraća da li je fixture podoban za pre-match refresh, odgovarajući interval i oznaku za završnu closing capturu.
- Implementirani prozori su: 24h, 12h, 6h, 2h i 30min, uz posebno označavanje poslednjih 15 minuta.
- Fixture-i nakon kickoff-a, bez timezone-aware datuma ili izvan 72-časovnog prozora se odbacuju.
- Dodat je `tests/workers/test_quote_refresh_schedule.py` sa proverama svih granica, prošlih fixture-a, 72h lookahead-a i timezone validacije.
- Testovi, Ruff i CI nisu pokrenuti u ovom okruženju.
- Commitovi: `402127765e4ba39cac7a594b10bc7ac03427b15e`, `b678d6b31bbc00454f1b989179517eb87c19a062`.

## 2026-09-15T12:30:00+02:00 — Production integracija kickoff-aware refresh scheduler-a

- `DiscoveredHistoryQuotePollingJob` sada koristi `QuoteRefreshScheduler` za selektivno osvežavanje kvota prema vremenu do kickoff-a.
- Discovery lookahead je postavljen na 72 sata.
- Novi fixture-i se odmah osvežavaju i registruju za naredni ciklus; poznati fixture-i se osvežavaju samo kada postanu due.
- Promena kickoff-a ponovo registruje fixture i računa novu cadence tačku.
- Greška jednog fixture-a ne prekida obradu ostalih fixture-a.
- Commitovi: `4f19c31c12c19dc818b765bd50ea9c49e1694af2`, `74c29742d2d6f054209bfdf42dfd41055168aa2e`.

## 2026-09-15T13:00:00+02:00 — Retry nakon neuspešnog prvog quote refresh-a

- Ispravljen je slučaj u kome neuspešan prvi refresh ostavlja fixture u memorijskom rasporedu i time sprečava retry u sledećem discovery ciklusu.
- Nakon greške uklanjaju se `known kickoff` marker i scheduler zapis, pa fixture ostaje ponovo podoban za inicijalni pokušaj.
- Dodat je/aktiviran test `test_retries_fixture_after_failed_refresh`.
- Commit: `e923015ea464f6fa82920bcefd018febf80dbec2`.

## 2026-09-15T13:20:00+02:00 — Keyword-only korekcija scheduler cleanup-a

- Ispravljen je poziv `QuoteRefreshScheduler.remove()` u `src/h2h/workers/discovered_history_quote_polling.py`.
- Metoda zahteva keyword-only argument `fixture_id`, pa je poziv promenjen u `remove(fixture_id=fixture_id)`.
- Korisnik je lokalno potvrdio uspešnu verifikaciju: `249 passed` i `uv run ruff check .` bez grešaka.
- Commit: `17e582fec78c1d510e1493f6963a438aa330a129`.

## 2026-09-15T14:00:00+02:00 — Real PostgreSQL integration coverage za quote history

- Dodat je `tests/integration/test_postgres_quote_history_integration.py`.
- Testovi koriste stvarni PostgreSQL kada je postavljen `QUANTBET_TEST_DATABASE_URL`; bez te promenljive se automatski preskaču.
- Pokriveni su:
  - konflikt prirodnog ključa za `quote_series`;
  - idempotentni ponovljeni upis iste serije;
  - konflikt sadržaja za postojeći `snapshot_id`;
  - konflikt prirodnog ključa za snapshot-e.
- Testovi nisu pokrenuti u ovom okruženju i nema potvrde da su prošli protiv stvarne baze.
- Commit: `f05effa718e46dfc17e4461ab6dbc8236c6a1560`.

## 2026-09-15T14:23:45+02:00 — Triage i remedijacija verification failure-a

- Scope je bio ograničen na 18 prethodno reprodukovanih verification failure-a i 7 Ruff nalaza; nije rađen novi repo-wide audit niti su menjani matematika, CI, bookmaker allowlist ili quote-history natural identity.
- Dva API-Football bookmaker failure-a potvrđena su kao production contract bug: `UnsupportedBookmakerError` je podklasa `ValueError` i adapter ga je nehotično prevodio u `QuoteNormalizationError`. Postojeći policy-boundary testovi, uvedeni uz mapping, potvrđuju da se policy exception propagira. Dodat je minimalni re-raise.
- Stale testovi i fixture-i su usklađeni sa aktuelnim enum, bookmaker, numeric-odd, timeout i natural-identity ugovorima; PostgreSQL fake cursor je ažuriran za `ANY(%s)`, one-parameter fixture query i snapshot natural-key read.
- Svih 7 Ruff nalaza u testovima je uklonjeno bez automatskog autofix-a: naive datetime test vrednost je formirana preko ISO parse-a, obsolete `noqa` direktive su uklonjene, a context manager-i su spojeni.
- Ciljani testovi: `101 passed, 6 skipped`.
- Konačna lokalna verifikacija: `uv run python -m ruff check .` → `All checks passed!`; `uv run python -m pytest --basetemp .verification-tmp/pytest` → `306 passed, 6 skipped, 0 failed, 0 errors`.
- PostgreSQL nije izvršen: nema `QUANTBET_TEST_DATABASE_URL` ni dostupnog lokalnog PostgreSQL/Docker servisa; šest integration testova ostaje očekivano preskočeno.
- Commitovi: `2e5ac1d25a8a13ed144a53f3593e2a19aaa20722`, `4386c6f8e674b6f01856f0b03934a922fd3d3f90`, `afeaea7f571aff4d345f19c553da8cd2b0eaee2a`, `002fca9881d3d13722b0f7b66aab508cffb411cb`.

## 2026-09-15T14:44:06+02:00 — Strukturna eligibility i registration granica

- Implementirano: `ValuePick -> EligibilityDecision -> register_pick() -> PickRegistration`.
- Dodati su `src/h2h/decisions/pick_eligibility.py` i `src/h2h/use_cases/register_pick.py`, sa testovima u `tests/decisions/test_pick_eligibility.py` i `tests/use_cases/test_register_pick.py`.
- Odluka je immutable, vezana za tačan `ValuePick`, sa eksplicitnim ID-jem i enum ishodom. Odbijanje zahteva machine-readable kod oblika `[A-Z][A-Z0-9_]*`; odobrenje ne sme nositi razlog odbijanja. Vokabular kodova pripada budućoj acceptance politici.
- Registracioni use-case odbija običan `ValuePick` i rejected odluku; approved odluka registruje isti objekat valuacije, bez mogućnosti zamene od strane pozivaoca.
- `PickRegistration` dobija opcioni keyword-only `eligibility_decision_id`. Use-case uvek čuva ID odobrene odluke; direktni domen-konstruktor ostaje kompatibilan i ne predstavlja dokaz da je gate korišćen. Postojeća ID/time validacija ostaje aktivna.
- Nije implementirano: acceptance politika, betting pragovi, de-vig, stake/risk pravila, povezivanje modela i quote-a, publisher ili persistencija odluka. Test approval objekti dokazuju strukturu, ne betting strategiju. Pun provenance iz decision contract-a ostaje budući posao.
- Ciljani testovi: `uv run python -m pytest tests/domain/test_value_pick.py tests/decisions/test_pick_eligibility.py tests/domain/test_pick_registration.py tests/use_cases/test_register_pick.py --basetemp .verification-tmp/targeted -o cache_dir=.verification-tmp/cache` -> **39 passed**.
- Ruff, jednom: `uv run python -m ruff check .` -> **All checks passed!**
- Full suite, jednom nakon ciljanih testova i Ruff-a: `uv run python -m pytest --basetemp .verification-tmp/pytest -o cache_dir=.verification-tmp/cache` -> **336 passed, 6 skipped, 0 failed, 0 errors** (342 prikupljena testa). Roditeljski temp direktorijum je napravljen pre testova; cache je usmeren u writable test direktorijum.
- Šest PostgreSQL integration testova ostaje preskočeno; PostgreSQL nije provisionovan. CI nije pokretan ovim zadatkom.
- Implementacioni commit: `09250378c27eec646862e9cba42af58cb239832f`.

## 2026-09-15T19:23:10+02:00 — PostgreSQL observation-identity remediation

- Base: `c934d8f6791f5c03025f83cdeb20b42f52f3d861`; review branch: `codex/postgres-observation-identity`. Main is not pushed or merged by this task.
- Classification F: fully migrated PostgreSQL runtime incompatibility. Restored `(series_id, observed_at, source)` in repository conflict target/lookup and in-memory natural identity; migrations 001/002 unchanged.
- `captured_at` is metadata, not immutable observation payload. Replay with same/different proposed ID or capture time preserves original row/ID/provenance; changed odd or incompatible reused ID conflicts.
- Integration bootstrap uses `apply_migrations()` and checks the complete migration chain, 002, and final uniqueness. Coverage now has 15 real-DB cases; fake-cursor tests remain control-flow checks only.
- Initial targeted run: 44 passed, 4 environment setup errors (missing external basetemp parent); after creating the parent: 48 passed. Ruff passed.
- One local full run: 356 passed, 1 failed, 15 skipped, 0 errors. The stale ingestion test still expected new capture time to legitimize a changed odd. It was corrected without changing ingestion production code.
- Final targeted run including ingestion: 51 passed; final Ruff passed. Full local suite not repeated.
- No local PostgreSQL URL/service; no provisioning or Railway changes. Existing CI is requested through draft PR #2; actual CI result is recorded in `CODEX_VERIFICATION_REPORT.md`.
- Implementation commit: `cea53a990c602c9d53d7a62ec64d8c62c92ef359`.
- Existing PR CI subsequently passed: [run 35000997862](https://github.com/Filip1994/v2quantbet/actions/runs/35000997862), job `104489067044`, PostgreSQL 16.15. Actual logs: 372 passed, 0 failed, 0 skipped, 0 errors, including all 15 integration cases; Ruff passed. No live Railway verification or concurrent-writer claim. Documentation-only follow-up preserves this tested code/test content.
