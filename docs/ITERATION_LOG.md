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
- Testovi и CI нису покренути у овом окружењу.
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

## 2026-09-15T05:00:00+02:00 — Kooperativno gašenje worker runtime-a

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

## 2026-09-15T06:30:00+02:00 — Izolacija grešaka po fixture-u u discovery worker-u

- Ažuriran je `src/h2h/workers/discovered_history_quote_polling.py`.
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
