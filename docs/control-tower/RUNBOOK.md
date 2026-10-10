# Football QuantBet operator: jedna strana

V1 je **samo za čitanje**, isključivo za `sincere-balance`. Svaki korak ispod je inspekcija postojećeg GitHub/Railway/dashboard stanja; restart, replay, deploy, promena varijabli, migracija i ručni DB upis zahtevaju poseban plan i odobrenje. [Aktivni registar](generated/football-2026-10-10/CONTROL_TOWER.md) razlikuje registrovan servis, cron, `RUNNING` instancu i uspešan deployment. Vreme snapshot-a je u svakom fajlu.

| Simptom | Prva provera | Sledeća provera | Kada eskalirati |
| --- | --- | --- | --- |
| Nema novih football pickova | `quantbet-engine` latest deployment + instance, `/livez`/readiness i worker heartbeat na postojećem dashboardu | fixture discovery freshness, API-Football quota i poslednji quote capture; zatim eligibility/pass reason u postojećoj analitici | Ako je worker stao, kvota neočekivano iscrpljena ili postoji DB greška. Nula pickova sama po sebi nije incident. |
| Stari podaci / nema kvota | Uporediti poslednji `observed_at` sa stvarnim vremenom i kickoffom; proveriti `quantbet-quantlab-collector` cron i football engine | Pregledati provider budget, watermark, poslednji uspešan job i eventualni rate limit | Ako je ciklus trebalo da radi, ali nema svežeg zapisa i razlog nije planirani stop. |
| Settlement kasni | `quantbet-engine` status, settlement heartbeat i rezultat fixture-a | Proveriti provider terminal status i finality delay; QuantLab ima odvojene shadow settlement činjenice | Ako je terminalni rezultat poznat, a nema napretka posle ugovorenog kašnjenja. Ne dopisivati rezultate ručno. |
| Deployment failed | Identifikovati tačan servis, commit, poslednji uspešan deployment i da li postoji `RUNNING` instanca | Proveriti CI za commit, migracioni korak, build/deploy log i korisnički signal | Ako je pogođen aktivni tok. Failed istorijski one-shot bez korisničkog uticaja nije automatski incident. |
| Model issue | Uporediti aktivni model ID/version i proveriti training/coverage status u read-only dashboardu | Point-in-time provenance, training target i test/CI rezultat za konkretan commit | Ako je model odsutan, nekompletan ili postoji mogući temporal leakage. Bez automatske aktivacije/rollbacka. |
| Broken data pipeline | Mapirati put `provider → collector → capture table → consumer` iz [fudbalskog dijagrama](generated/football-2026-10-10/architecture.mmd) | Proveriti cron schedule, zadnji uspešan run, DB konekciju i table freshness; bez čitanja tajni | Ako su dva uzastopna očekivana ciklusa propuštena ili je izlaz nepotpun. |

## Pravilo odluke

1. Zabeleži UTC vreme, servis ID, commit/deployment ID, simptom i relevantan log ili dashboard link.
2. Razdvoji **config/deploy stanje**, **proces**, **job uspeh**, **svežinu podataka** i **korisnički uticaj**. Jedno ne dokazuje drugo.
3. Za cron proveri raspored i poslednji uspešan ciklus; `EXITED` posle uspešnog jednokratnog posla je očekivan.
4. Pre bilo kakve intervencije proveri koje druge komponente koriste isti PostgreSQL, API budget ili izlaz. Production i shadow laboratorije nisu ista P&L knjiga.
5. Napravi incident belešku sa hipotezom i dokazima. Za restart/redeploy/rollback, promenu quota ili DB mutaciju traži odobrenje i zaseban reviewable plan.

**Merge gate:** i dokumentacioni merge u `main` može pokrenuti Railway auto-deploy. PR #243 je u 11:58 UTC pokrenuo `quantbet-kellylab`, uključujući predeploy sa `applied 0 migration(s)`. Railway pregled je potvrdio `build.watchPatterns` na 14/15 GitHub servisa; KellyLab je jedini bez filtera, a neki postojeći filteri propuštaju deljene runtime zavisnosti. [Predlog po servisu](DEPLOYMENT_GUARD_PROPOSAL.md) je samo plan. PR #244 ostaje draft do zasebnog odobrenja zaštite i merge-a. Sam prolaz CI nije dovoljan.

## Aktivni collector incident, read-only presek oko 16:53 UTC

- Poslednji potvrđeni puni ciklus završio je u 09:49:40 UTC, nakon početka u 08:01. Ciklusi 11–16 UTC nisu prijavili `cycle completed`; poslednji deployment `924be963-a368-48df-91b0-41331632f053` je `CRASHED` u 16:06:53 UTC. Poslednji log je GoalLab `history_loaded rows=30000`, bez Python traceback-a. OOM je hipoteza, ne potvrđen exit reason: limit 0,750 GB, maksimum 12-časovne serije 0,748 GB.
- Poslednji `quantlab_market_captures` i fixture/discovery capture u bazi je 08:01:22 UTC. Svežina se proverava vremenom reda, ne samo statusom deploymenta. Goal/Corner/Card/H2H su radili u prethodnom punom ciklusu; redovan rad posle njega nije potvrđen. Delimične Goal decisions iz kasnijih pokušaja nisu dokaz punog ciklusa.
- Bez odobrenja **ne** menjati collector RAM, cron, varijable, modele, podatke ili replay. Za incident zabeležiti poslednji kompletan ciklus, ID neuspelog deploymenta, post-history log, peak RAM/limit, DB watermarks i eventualni kernel exit reason. [Puni nalaz](STABILIZATION_REVIEW_2026-10-10.md) i [draft dijagnostika #248](https://github.com/Filip1994/v2quantbet/pull/248).

## Backup i privilegije

Football PostgreSQL ima jednu login rolu `postgres` sa superuser pravima; 16/17 ne-DB servisa deli njene kredencijale. PITR/HA su isključeni; read-only Railway volume backup **i schedule liste su prazne**. Eventualni eksterni dump ostaje nepoznat. Dok ne postoji checksum plus izolovan restore dokaz, ne tvrditi da je recovery moguć. Nema rutinskog SQL write-a, `pg_dump`-a, grant/role promene ili restore-a u ovom vodiču. [Matrica prava #250](https://github.com/Filip1994/v2quantbet/pull/250) i [backup/restore plan #249](https://github.com/Filip1994/v2quantbet/pull/249) traže posebno operativno odobrenje.

**Troškovni gate:** Railway infrastructure hard limit je $40, trenutni period oko $32,99 i procena oko $33,51 do kraja perioda (presek 10. oktobra). Agent budget je druga kvota. Pre aktivacije backup-a/PITR-a ili izolovanog restore-a ponovo proveriti trošak i ostaviti najmanje $2 rezerve u infrastructure limitu; bez automatskog povećanja cap-a.

## Bezbedne read-only komande

```text
railway status -p c0aa8208-dd61-48c4-a1d8-488802e84f36 -e production --json
git log -n 20 --oneline
python scripts/control_tower.py build --fixture docs/control-tower/fixtures/football-2026-10-10-0950.json --out <local-output-directory>
```

Railway CLI izlaz može sadržati komande i konfiguracioni tekst: nemoj ga lepiti u javni issue ili PR. Control Tower generator upisuje samo dozvoljena, sanitizovana polja. Nikad ne pokretati `railway run`, `railway up`, `railway restart`, `railway redeploy`, DB shell ili migration komandu u rutinskom dijagnostičkom koraku. `railway variable list --json` vraća stvarne tajne; koristiti ga samo za ciljanu proveru prava pristupa uz privatnu, sanitizovanu obradu izlaza.
