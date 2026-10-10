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

**Merge gate:** i dokumentacioni merge u `main` može pokrenuti Railway auto-deploy. PR #243 je u 11:58 UTC pokrenuo `quantbet-kellylab`, uključujući predeploy sa `applied 0 migration(s)` ([dokaz i predlog](DEPLOYMENT_GUARD_PROPOSAL.md)). PR #244 ostaje draft dok vlasnik zasebno ne odobri zaštitu Railway okidača i merge. Sam prolaz CI nije dovoljan.

## Bezbedne read-only komande

```text
railway status -p c0aa8208-dd61-48c4-a1d8-488802e84f36 -e production --json
git log -n 20 --oneline
python scripts/control_tower.py build --fixture docs/control-tower/fixtures/football-2026-10-10-0950.json --out <local-output-directory>
```

Railway CLI izlaz može sadržati komande i konfiguracioni tekst: nemoj ga lepiti u javni issue ili PR. Control Tower generator upisuje samo dozvoljena, sanitizovana polja. Nikad ne pokretati `railway run`, `railway up`, `railway restart`, `railway redeploy`, DB shell ili migration komandu u rutinskom dijagnostičkom koraku. `railway variable list --json` vraća stvarne tajne; koristiti ga samo za ciljanu proveru prava pristupa uz privatnu, sanitizovanu obradu izlaza.
