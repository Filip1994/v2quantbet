# Railway deployment zaštita — predlog za odobrenje

**Opseg:** samo `sincere-balance`, production environment `e08eafba-5581-4ddd-90b7-b0d456ce6cf9`, repo `Filip1994/v2quantbet`. **Status:** plan; Railway konfiguracija, merge i deployment nisu menjani. PR #244 ostaje draft.

## Potvrđeno stanje, 10. oktobar 2026.

- Docs-only merge PR #243 (`4842946`) pokrenuo je KellyLab deployment `f7780cc5-37d8-4c94-b97f-2c80afc01c69`. Predeploy `python -m h2h.migrate` prijavio je `applied 0 migration(s)`.
- Svih 15 GitHub povezanih definicija prati `v2quantbet`: 14 prati `main`, jedna ops granu; `source.checkSuites=false` za sve. **Ispravka ranijeg nalaza:** 14 ima `build.watchPatterns`, samo KellyLab nema. Pregled samo `source.watchPaths` nije obuhvatio stvarno Railway polje.
- KellyLab nema filter i zato je dokumentacioni commit izazvao build/deploy. Ostali servisi mogu imati `SKIPPED` GitHub deployment zapis, što nije izvršen runtime deploy. Osam servisa ima predeploy migracioni korak.
- Railway [watch paths](https://docs.railway.com/builds/build-configuration#configure-watch-paths) su gitignore obrasci od korena repo-a; commit bez podudaranja preskače deployment. [GitHub autodeploy](https://docs.railway.com/deployments/github-autodeploys) prati povezanu granu. CI path filter ne kontroliše Railway.

## Tačne zamenske liste

Sledeće su **potpune zamenske vrednosti** za `build.watchPatterns`, ne usputni dodaci. Zajednički skupovi su doslovni obrasci koji se dodaju navedenom redu bez duplikata:

```text
P = pyproject.toml | uv.lock | .python-version | src/h2h/__init__.py
M = migrations/** | src/h2h/migrate.py | src/h2h/persistence/migrations.py | src/h2h/persistence/postgres_runtime.py
R = railway.json
```

`R` je konzervativan: korenski `railway.json` je podrazumevani config-as-code fajl. Railway read-only config nije pokazao putanju za imenovane `railway.*.json` fajlove; njihove veze sa servisima su **pretpostavka** i moraju se potvrditi u Deployment Details pre primene. Fajlovi su uključeni da relevantna config promena ne bude preskočena. Railway varijable, start komande i resource limiti mogu pokrenuti deployment **nezavisno od Git watch paths**.

| Servis (ID skraćen) | Zameniti `build.watchPatterns` sa | Obrazloženje |
| --- | --- | --- |
| `quantbet-engine` (`3204398e`) | P + M + R + `src/h2h/**` | Engine statički doseže Production i deljene Research/QuantLab module. |
| `quantbet-dashboard` (`69a60980`) | P + R + `railway.dashboard.json` + `src/h2h/dashboard_entrypoint.py` + `src/h2h/api/dashboard.py` + `src/h2h/api/dashboard_time.py` + `src/h2h/domain/**` + `src/h2h/persistence/**` + `src/h2h/workers/**` + `src/h2h/logging_config.py` + `src/h2h/api/__init__.py` + `src/h2h/production_buckets.py` | Stvarni dashboard importi; nema predeploy migracije. |
| `quantbet-research` (`2965d3a3`) | P + M + R + `railway.research.json` + `src/h2h/research_dashboard_entrypoint.py` + `src/h2h/api/research_dashboard.py` + `src/h2h/api/research_analytics.py` + `src/h2h/api/dashboard_time.py` + `src/h2h/domain/**` + `src/h2h/persistence/postgres_research_signals.py` + `src/h2h/workers/runtime.py` + `src/h2h/logging_config.py` + `src/h2h/api/__init__.py` + `src/h2h/persistence/__init__.py` + `src/h2h/workers/__init__.py` + `src/h2h/production_buckets.py` | Dodaje migration runner i deljene domain module. |
| `quantbet-quantlab` (`34662406`) | P + M + R + `railway.quantlab-dashboard.json` + `src/h2h/quantlab_dashboard_entrypoint.py` + `src/h2h/quantlab/**` + `src/h2h/domain/**` + `src/h2h/persistence/postgres_production_funnel.py` + `src/h2h/workers/runtime.py` + `src/h2h/logging_config.py` + `src/h2h/persistence/__init__.py` + `src/h2h/workers/__init__.py` + `src/h2h/production_buckets.py` | Dashboard importuje QuantLab repository i lab prikaze. |
| `quantbet-quantlab-collector` (`349ad868`) | P + M + R + `railway.quantlab-collector.json` + `src/h2h/quantlab/**` + `src/h2h/archive/**` + `src/h2h/odds/**` + `src/h2h/domain/**` + `src/h2h/persistence/**` + `src/h2h/quant/**` + `src/h2h/use_cases/**` + `src/h2h/workers/runtime.py` + `src/h2h/logging_config.py` + `src/h2h/workers/__init__.py` + `src/h2h/production_buckets.py` | Import graf doseže arhivu, odds, persistence i use cases; postojeći filter ih propušta. |
| `quantbet-quantlab-modeler` (`793608ac`) | P + M + R + `railway.quantlab-modeler.json` + `src/h2h/quantlab/**` + `src/h2h/domain/**` + `src/h2h/persistence/**` + `src/h2h/quant/**` + `src/h2h/logging_config.py` | Trening i deljeni moduli. |
| `quantbet-kellylab` (`15a796eb`) | P + M + R + `railway.kellylab.json` + `src/h2h/kellylab_dashboard_entrypoint.py` + `src/h2h/api/kellylab_dashboard.py` + `src/h2h/api/dashboard_time.py` + `src/h2h/persistence/postgres_kellylab.py` + `src/h2h/domain/competition_scope.py` + `src/h2h/workers/runtime.py` + `src/h2h/logging_config.py` + `src/h2h/api/__init__.py` + `src/h2h/domain/__init__.py` + `src/h2h/persistence/__init__.py` + `src/h2h/workers/__init__.py` + `src/h2h/kellylab.py` + `src/h2h/production_buckets.py` | Sada nema filter; ovo zatvara dokazani docs-only okidač. |
| `quantbet-archive-lifecycle` (`fdb9a387`) | P + M + R + `Dockerfile` + `railway.archive-lifecycle.json` + `src/h2h/archive/**` + `src/h2h/logging_config.py` | Docker build kopira `src` i `migrations`; postojeći filter propušta migracije. |
| `quantbet-find-26a813a9b6` (`9cd6573b`) | P + R + `src/h2h/archive/**` | Archive one-shot bez predeploy migracije; potvrditi vlasnika pre primene. |
| `quantbet-quantlab-collector-ACut` (`e0923ec8`) | **Zadržati:** `__disabled_quantlab_collector_duplicate__` | Rezervni cron je namerno bez Git auto-deploya. |
| `goallab-void-26a813a9b6` (`055d5dd9`) | **Zadržati:** `__disabled_goallab_void__` | Inertni one-shot. |
| `quantbet-void-1636701` (`7845d562`) | **Zadržati:** `__manual_void_1636701__` | Ručni Docker dijagnostički servis. |
| `quantbet-find2-26a813a9b6` (`d963a123`) | **Zadržati:** `__disabled_quantbet_find2__` | Ručni dijagnostički servis. |
| `south-america-performance-query-v2` (`eb56e80e`) | **Zadržati:** `__disabled_south_america_query__` | Ručni dijagnostički servis. |
| `quantbet-void-1636701-ops` (`9b6e43d2`) | **Zadržati:** `__disabled_void_1636701__` | Zasebna ops grana. |

`Postgres` je image servis; `south-america-performance-query` i `quantbet-kelly-tournament` su Railway Functions bez GitHub source grane. Git watch paths nisu primenljivi. Nijedan servis se ne briše.

`docs/**`, `tests/**`, `scripts/control_tower.py`, `.github/**`, korenski Markdown i sanitizovani snapshotovi nisu runtime ulazi navedenih servisa i treba da budu `SKIPPED`. Novi runtime folder, config ili asset mora dobiti odgovarajući obrazac u istom PR-u pre merge-a.

## Test i rollout tek posle odobrenja

1. Sačuvati live `branch`, `build.watchPatterns`, builder, stvarni config-source, predeploy, poslednji stabilan deployment/SHA i cron status. Ponovo pregledati import graf i dinamičke importove. Ako se stanje promenilo, ažurirati ovaj plan.
2. Pokrenuti `uv run --with pytest python -m pytest tests/test_deployment_guard_plan.py -q` za proveru statičkog import grafa i sledeću offline scenario matricu: `docs/control-tower/RUNBOOK.md`, `tests/test_control_tower.py`, `.github/workflows/ci.yml`, `scripts/control_tower.py` → svi `SKIPPED`; `src/h2h/quantlab/goal_lab/model.py` → engine, QuantLab dashboard/collector/modeler; `src/h2h/archive/object_store.py` → engine, collector, archive lifecycle i archive one-shot; `src/h2h/persistence/migrations.py` i novi `migrations/067_*.sql` → sedam aktivnih servisa sa migracionim predeployom, dok rezervni ACut ostaje namenski `SKIPPED`; `src/h2h/persistence/postgres_kellylab.py` → KellyLab; `Dockerfile` → archive lifecycle.
3. Primeniti samo odobrene redove, prvo KellyLab. Proveriti Railway staged diff i sačuvati prethodne liste. Sam config edit može izazvati deploy; planirati prozor i proveriti migration log, health i cron. Ostale redove uvoditi postupno, bez paralelne promene rama, cron-a ili kredencijala.
4. U odobrenom release-u proveriti stvarnu Railway semantiku na docs-only commitu (`SKIPPED`) i malom runtime commitu (samo očekivani servisi); povezati SHA, build, predeploy, health i cron rezultat. PR #244 ostaje draft do ove potvrde i posebnog merge odobrenja.

**Rollback:** ako potreban runtime commit bude preskočen, vratiti prethodnu listu samo pogođenom servisu i uz posebno odobrenje ručno deploy-ovati pregledani SHA. Ako docs-only commit pokrene neočekivani servis, zaustaviti rollout i istražiti config-source/dinamičke zavisnosti. Prazna watch lista vraća široki auto-deploy rizik. DB migracije se ne vraćaju automatskim Git rollbackom.
