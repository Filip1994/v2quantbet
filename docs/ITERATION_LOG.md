# QuantBet — Iteration Log

Ovaj dokument beleži manje korake rada na projektu, uključujući read-only preglede, analize, odluke, implementacije, testove, CI provere i dokumentacione izmene.

## Pravila vođenja

- Svaka radna iteracija dobija zaseban unos.
- Unos se piše ljudski čitljivim jezikom.
- Navodi se šta je provereno ili urađeno, bez predstavljanja planiranog rada kao završenog.
- Za implementacione iteracije beleže se izmenjeni fajlovi, testovi, CI rezultat i commit kada su dostupni.
- Svaki unos sadrži timestamp u ISO 8601 formatu.
- `docs/PROGRESS.md` ostaje sažeti pregled većih završenih celina; ovaj dokument čuva detalje manjih koraka.

## 2026-09-14T00:00:00Z — Uveden dnevnik iteracija

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
- Commit: `0c49185495acf8779424e71583442e5cd137fe9d`.
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
- Pokušaj ažuriranja `src/h2h/domain/__init__.py` nije uspeo zbog SHA mismatch-a; export modela još nije završen.
- CI nije proveravan u ovoj iteraciji.
- Commit modela: `c0c52785afd82f1502800b500dc04f3a92f638f1`.
- Commit testova: `013d384d8543888e11ab12eacd6f38518d4d9726`.
