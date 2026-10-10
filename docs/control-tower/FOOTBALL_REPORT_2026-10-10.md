# Football Control Tower: aktivni opseg i provereni rizici

**Opseg:** samo `sincere-balance` / production (`c0aa8208-dd61-48c4-a1d8-488802e84f36`, environment `e08eafba-5581-4ddd-90b7-b0d456ce6cf9`). Ovaj izveštaj razdvaja sanitizovani presek od 09:50 UTC, kasnije read-only Railway metapodatke i nepoznanice. Raniji [Phase A audit](ARCHITECTURE_AUDIT_2026-10.md) i [follow-up](FOLLOWUP_2026-10-10.md) su istorijski, zamenjeni za aktivni opseg. Nijedan drugi projekat nije deo ovog izveštaja.

## Obuhvat i arhitektura

Iz [09:50 fixture-a](fixtures/football-2026-10-10-0950.json) deterministički [generator](../../scripts/control_tower.py) daje **18/18** registrovanih Railway definicija, **8/18** detaljno mapiranih po kriterijumu vlasnik + svrha + dokaz + kodni put, **10/18** `unmapped`, **15/18** Git source ref-ova, **8/18** prepoznatih `python -m` entrypointa, **4** cron definicije, **8** servisa sa `RUNNING` instancom u tom trenutku i **1** poslednji `FAILED/CRASHED` deployment. Ograničeni [GitHub fixture](fixtures/football-github-2026-10-10.json) povezuje CI run istog SHA za **4/18** servisa (engine, dashboard, research, KellyLab); za ostale CI veza nije potvrđena. Ovo su definicije i metapodaci, ne uptime, uspešnost poslova ili ekonomski rezultat. [Registar](generated/football-2026-10-10/CONTROL_TOWER.md), [Mermaid graf](generated/football-2026-10-10/architecture.mmd), [ručni scorecard](assessment.json) i [opaženi diff](generated/football-observed-diff/SNAPSHOT_DIFF.md) koriste samo fudbalske ulaze.

U read-only Railway inventaru oko 12:30 UTC postoji istih 18 definicija bez staged promena. Production engine, dashboard, research, QuantLab dashboard/collector/modeler, KellyLab, archive lifecycle, football PostgreSQL i jednokratni/diagnostički servisi su u jednom projektu. `quantbet-kelly-tournament` je Railway Function na image source-u, pa nije deo GitHub autodeploy broja. `quantbet-void-1636701-ops` prati posebnu granu. Opaženi diff od 01:47 do 09:50 pokazuje samo da je collector prešao sa 1 na 0 `RUNNING` instanci; ne pokazuje kvar.

## Deployment i predeploy

Dokumentacioni merge [#243, SHA `4842946`](https://github.com/Filip1994/v2quantbet/commit/48429464389259c65415ef7195d5819b1632379f) odgovara KellyLab Railway deploymentu `f7780cc5-37d8-4c94-b97f-2c80afc01c69` u 11:58:07 UTC. Deployment je `SUCCESS`; log u 11:58:25 UTC beleži `applied 0 migration(s)` pre uspešnog `/livez` healthchecka. Zato je **predeploy pokrenut i završio bez novih migracija**. Ne tvrdimo da je svaka istorijska predeploy komanda uspela niti da deployment status dokazuje ispravnost podataka. Railway konfiguracija za povezane servise i minimalni predlog zaštite navedeni su u [posebnom predlogu](DEPLOYMENT_GUARD_PROPOSAL.md). PR #244 ostaje draft dok se okidač za `main` ne zaštiti uz odobrenje.

## Zajednički PostgreSQL i oporavak

[Ranija ciljna read-only provera](FOLLOWUP_2026-10-10.md#p1-production--quantlab-db-izolacija) uporedila je razrešene `DATABASE_URL` vrednosti engine-a i QuantLab collector-a i collector-ov alias: isti host, baza, korisnik i lozinka. Trenutni konektor vraća samo imena varijabli, ali potvrđuje da oba servisa imaju `DATABASE_URL` i collector ima `QUANTBET_QUANTLAB_DATABASE_URL`. Kod engine kompozicije i collector entrypointa koristi `DATABASE_URL`; [migracioni entrypoint](../../src/h2h/migrate.py) takođe čita taj naziv. Jedan zajednički PostgreSQL nalog ima isti efektivni skup grantova u oba procesa. **Tačan blast radius nije utvrđen:** nema uspešnog read-only SQL pregleda `current_user`, članstva rola, `has_table_privilege`, schema prava, default privileges ili eventualnog `SET ROLE`. Ne tvrdimo da collector može menjati svaku produkcionu tabelu.

Sledeći korak uz odobren DB pristup je samo read-only inventar grantova po tabeli/šemi i provera pod kojom se rolom izvršava migracija. Zatim, kroz zaseban migracioni plan i test u izolovanom okruženju, odvojiti nalog za migracije, Production runtime i QuantLab collector, dajući collector-u samo potrebne `quantlab_*` read/write privilegije. U ovom PR-u nema role, grant, credential ili schema promene.

Za **fudbalski PostgreSQL** je read-only `railway postgres pitr status --json` 2026-10-10 vratio `enabled=false` i `bucketWired=false`; `railway postgres ha status --json` vratio je `isCluster=false` i jednog člana. PostgreSQL ima montirani `postgres-volume` (102400 MB). Projekat ima i bucket `durable-barrel`, ali nema dokaza da on čuva DB backup. Postojanje drugih snapshot/export backup-a, poslednji uspešan artefakt, retention, RPO/RTO i uspešan izolovani restore su **nepoznati**. Potreban je read-only inventar backup politike i artefakata, pa poseban plan za restore probu; ništa nije restaurirano.

## Cron i dijagnostičke definicije

Četiri cron definicije u 09:50 preseku su QuantLab collector (`0 * * * *`), modeler (`15 */12 * * *`), collector-ACut (`0 0 1 1 *`) i archive lifecycle (`40 * * * *`). Za svaku je u registru odvojeno: raspored, trenutna instanca, poslednji direktno dokazan uspešan završetak i potvrđena svežina podataka. Poslednja dva polja su `unknown`. Collector je u kasnijem read-only inventaru imao novi poslednji deployment `CRASHED` (12:03 UTC); to zahteva ciljanu proveru poslednjeg exit razloga i watermarka, ali samo po sebi ne dokazuje prekid toka podataka.

Sledeće definicije zahtevaju vlasnika, poslednje **stvarno završeno izvršavanje** i potvrđenog consumer-a pre bilo kakvog lifecycle predloga. `SUCCESS` ispod je status poslednjeg deploymenta u 09:50 fixture-u, **ne** dokaz uspešnog izvršavanja; poslednji završetak i consumer su `unknown` gde nema zasebnog dokaza.

| Definicija | Kod/source dokaz | Poslednji deployment u fixture-u | Uspešno izvršavanje / consumer |
| --- | --- | --- | --- |
| `goallab-void-26a813a9b6` | `v2quantbet` ref; entrypoint unknown | `SUCCESS` 2026-09-29 00:59 UTC | unknown / unknown |
| `quantbet-void-1636701` | `v2quantbet` ref; entrypoint unknown | `FAILED` 2026-10-01 23:46 UTC | unknown / unknown |
| `quantbet-void-1636701-ops` | `v2quantbet@ops/void-1636701`; entrypoint unknown | `SUCCESS` 2026-10-01 23:52 UTC | unknown / unknown |
| `quantbet-find-26a813a9b6` | `v2quantbet` ref; `h2h.archive.entrypoint` | `SUCCESS` 2026-10-09 23:38 UTC | unknown / unknown |
| `quantbet-find2-26a813a9b6` | `v2quantbet` ref; entrypoint unknown | `SUCCESS` 2026-09-29 00:59 UTC | unknown / unknown |
| `south-america-performance-query` | Railway Function image; repo ref unknown | `SUCCESS` 2026-10-10 00:30 UTC | unknown / unknown |
| `south-america-performance-query-v2` | `v2quantbet` ref; entrypoint unknown | `SUCCESS` 2026-10-02 22:50 UTC | unknown / unknown |

`quantbet-kelly-tournament`, football `Postgres` i `quantbet-quantlab-collector-ACut` čine preostale tri `unmapped` definicije po strogom kriterijumu; to ne znači da su nepotrebne. Nema predloga za brisanje. Za operativni postupak vidi [runbook](RUNBOOK.md).
