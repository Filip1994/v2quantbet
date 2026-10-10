# Football Control Tower: aktivni opseg i provereni rizici

**Opseg:** samo `sincere-balance` / production (`c0aa8208-dd61-48c4-a1d8-488802e84f36`, environment `e08eafba-5581-4ddd-90b7-b0d456ce6cf9`). Ovaj izveštaj razdvaja sanitizovani presek od 09:50 UTC, kasnije read-only Railway metapodatke i nepoznanice. Raniji [Phase A audit](ARCHITECTURE_AUDIT_2026-10.md) i [follow-up](FOLLOWUP_2026-10-10.md) su istorijski, zamenjeni za aktivni opseg. Nijedan drugi projekat nije deo ovog izveštaja.

## Obuhvat i arhitektura

Iz [09:50 fixture-a](fixtures/football-2026-10-10-0950.json) deterministički [generator](../../scripts/control_tower.py) daje **18/18** registrovanih Railway definicija, **8/18** detaljno mapiranih po kriterijumu vlasnik + svrha + dokaz + kodni put, **10/18** `unmapped`, **15/18** Git source ref-ova, **8/18** prepoznatih `python -m` entrypointa, **4** cron definicije, **8** servisa sa `RUNNING` instancom u tom trenutku i **1** poslednji `FAILED/CRASHED` deployment. Ograničeni [GitHub fixture](fixtures/football-github-2026-10-10.json) povezuje CI run istog SHA za **4/18** servisa (engine, dashboard, research, KellyLab); za ostale CI veza nije potvrđena. Ovo su definicije i metapodaci, ne uptime, uspešnost poslova ili ekonomski rezultat. [Registar](generated/football-2026-10-10/CONTROL_TOWER.md), [Mermaid graf](generated/football-2026-10-10/architecture.mmd), [ručni scorecard](assessment.json) i [opaženi diff](generated/football-observed-diff/SNAPSHOT_DIFF.md) koriste samo fudbalske ulaze.

U read-only Railway inventaru postoji istih 18 definicija bez staged promena. Production engine, dashboard, research, QuantLab dashboard/collector/modeler, KellyLab, archive lifecycle, football PostgreSQL i jednokratni/dijagnostički servisi su u jednom projektu. `quantbet-kelly-tournament` je Railway Function na image source-u, pa nije deo GitHub autodeploy broja. `quantbet-void-1636701-ops` prati posebnu granu. Opaženi diff od 01:47 do 09:50 pokazuje samo da je collector prešao sa 1 na 0 `RUNNING` instanci; ne pokazuje kvar.

## Deployment i predeploy

Dokumentacioni merge [#243, SHA `4842946`](https://github.com/Filip1994/v2quantbet/commit/48429464389259c65415ef7195d5819b1632379f) odgovara KellyLab Railway deploymentu `f7780cc5-37d8-4c94-b97f-2c80afc01c69` u 11:58:07 UTC. Deployment je `SUCCESS`; log u 11:58:25 UTC beleži `applied 0 migration(s)` pre uspešnog `/livez` healthchecka. Zato je **predeploy pokrenut i završio bez novih migracija**. Ne tvrdimo da je svaka istorijska predeploy komanda uspela niti da deployment status dokazuje ispravnost podataka. Railway konfiguracija za povezane servise i minimalni predlog zaštite navedeni su u [posebnom predlogu](DEPLOYMENT_GUARD_PROPOSAL.md). PR #244 ostaje draft dok se okidač za `main` ne zaštiti uz odobrenje.

## Zajednički PostgreSQL i oporavak

[Ciljna read-only provera](FOLLOWUP_2026-10-10.md#p1-production--quantlab-db-izolacija) uporedila je razrešene `DATABASE_URL` vrednosti engine-a i QuantLab collector-a i collector-ov alias: isti host, baza, korisnik i lozinka. Naknadni SQL inventar je potvrdio da je jedina aplikaciona login rola `postgres`, sa `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION` i `BYPASSRLS`; ona poseduje svih 79 public tabela i 13 funkcija. Šesnaest od 17 ne-DB servisa deli iste razrešene kredencijale. To potvrđuje visok blast radius, bez tvrdnje da je zabeležen neovlašćen upis.

Zasebni draft [#250](https://github.com/Filip1994/v2quantbet/pull/250) predlaže table/grant matricu, izolovane testove i faznu rotaciju tek posle backup/restore dokaza. U ovom PR-u nema role, grant, credential ili schema promene.

Za **fudbalski PostgreSQL** read-only provera je vratila `PITR enabled=false`, `HA isCluster=false`, `volumeInstanceBackupList=[]` i `volumeInstanceBackupScheduleList=[]`. Montirani volume ima 102400 MB; baza je ~19,48 GB. Dakle nema Railway volume snapshotova ili schedule-a. Eventualni spoljašnji dump i izolovani restore ostaju **nepoznati**. `durable-barrel` je app cold archive, ne DB backup. Draft [#249](https://github.com/Filip1994/v2quantbet/pull/249) sadrži tačan backup/restore plan, retention i troškovni gate; ništa nije aktivirano ili restaurirano.

## Cron i dijagnostičke definicije

Četiri cron definicije u 09:50 preseku su QuantLab collector (`0 * * * *`), modeler (`15 */12 * * *`), collector-ACut (`0 0 1 1 *`) i archive lifecycle (`40 * * * *`). Za svaku je u registru odvojeno: raspored, trenutna instanca, poslednji direktno dokazan uspešan završetak i potvrđena svežina podataka. Ta polja u **starom fixture-u** ostaju `unknown`; naknadna ciljna provera je potvrdila collector `cycle completed` u 09:49 UTC, neuspele pokušaje 11–16 UTC i core market/fixture watermark 08:01:22 UTC u SQL preseku oko 16:53. [Incident detalji](STABILIZATION_REVIEW_2026-10-10.md) i dijagnostički draft [#248](https://github.com/Filip1994/v2quantbet/pull/248) razlikuju cron, modeler i prikupljanje.

Sledeće definicije zahtevaju vlasnika, poslednje **stvarno završeno izvršavanje** i potvrđenog consumer-a pre bilo kakvog lifecycle predloga. `SUCCESS` ispod je status poslednjeg deploymenta u 09:50 fixture-u, **ne** dokaz uspešnog izvršavanja; poslednji završetak i consumer su `unknown` gde nema zasebnog dokaza.

| Definicija | Kod/source dokaz | Poslednji deployment u fixture-u | Uspešno izvršavanje / consumer |
| --- | --- | --- | --- |
| `goallab-void-26a813a9b6` | Git, `true` start, disabled watch sentinel; inertni one-shot | `SUCCESS` 2026-09-29 00:59 UTC | unknown / unknown |
| `quantbet-void-1636701` | Git/Dockerfile, ručni sentinel; jednokratni read-only `research_signals` upit | `FAILED` 2026-10-01 23:46 UTC | unknown / unknown |
| `quantbet-void-1636701-ops` | Git `ops/void-1636701`, disabled sentinel; namena nije dokazana | `SUCCESS` 2026-10-01 23:52 UTC | unknown / unknown |
| `quantbet-find-26a813a9b6` | `h2h.archive.entrypoint`, Git watch archive; tačan mode nepoznat | `SUCCESS` 2026-10-09 23:38 UTC | unknown / unknown |
| `quantbet-find2-26a813a9b6` | Git, disabled sentinel; jednokratni read-only agregat lab performansi | `SUCCESS` 2026-09-29 00:59 UTC | unknown / unknown |
| `south-america-performance-query` | Railway Function image; read-only CornerLab upit | `SUCCESS` 2026-10-10 11:51 UTC | unknown / unknown |
| `south-america-performance-query-v2` | Git, disabled sentinel; read-only CornerLab upit uprkos nazivu | `SUCCESS` 2026-10-02 22:50 UTC | unknown / unknown |
| `quantbet-kelly-tournament` | Railway Function image; HTTP shadow eksperiment, bez Git watch | `SUCCESS` 2026-10-10 01:05 UTC | unknown / unknown |
| `Postgres` | Railway image + persistent volume; osnovna DB zavisnost | `SUCCESS` 2026-09-28 | DB query potvrđen / 16 servisa dele nalog |
| `quantbet-quantlab-collector-ACut` | Git, disabled watch sentinel, godišnji rezervni cron; ima predeploy migraciju | status ne koristi se kao dokaz aktivnog ciklusa | unknown / unknown |

Ovo je read-only klasifikacija namene po konfiguraciji, ne potvrda vlasnika ili potrošača. `SUCCESS` je status deploymenta, ne dokaz uspešnog jednokratnog izvršavanja. Strogi Control Tower score i dalje označava 10 definicija kao `unmapped` dok vlasnik, stvarni završetak i consumer nisu dokazani. Nema predloga za brisanje. Za operativni postupak vidi [runbook](RUNBOOK.md).
