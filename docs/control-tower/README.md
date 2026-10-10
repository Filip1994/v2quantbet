# Football Control Tower V1

Aktivni opseg je isključivo Railway projekat `sincere-balance` (`c0aa8208-dd61-48c4-a1d8-488802e84f36`) i repozitorijum `Filip1994/v2quantbet`. CLI radi offline iz sanitizovanih ulaza, samo čita metapodatke i ne pokreće servis. Pogrešan ili nedostajući identitet projekta zaustavlja `capture-railway`, `build` i `diff`. GitHub capture prihvata samo `v2quantbet`.

Novi read-only nalazi za collector, DB grantove i backup su u [stabilizacionom pregledu](STABILIZATION_REVIEW_2026-10-10.md). Generisani registar ispod je stariji, sanitizovani presek od 09:50 UTC i ne predstavlja live stanje u 14:30 UTC.

[Aktivni fudbalski izveštaj](FOOTBALL_REPORT_2026-10-10.md), [generisani registar](generated/football-2026-10-10/CONTROL_TOWER.md), [graf](generated/football-2026-10-10/architecture.mmd), [diff](generated/football-observed-diff/SNAPSHOT_DIFF.md), [runbook](RUNBOOK.md) i [predlog zaštite deploymenta](DEPLOYMENT_GUARD_PROPOSAL.md) čine aktuelni pogled. [Phase A audit](ARCHITECTURE_AUDIT_2026-10.md), [prvobitni servisni inventar](SERVICE_INVENTORY.md), [ranije follow-up beleške](FOLLOWUP_2026-10-10.md), stari višesportski fixture fajlovi i stari `generated/2026-10-10`, `generated/observed-diff` i `generated/synthetic-*` izlazi su **istorijski, zamenjeni i van trenutnog opsega**. Čuvaju se samo radi sledljivosti; ne predstavljaju današnje fudbalske brojeve.

## Determinističko obnavljanje bez tokena

Iz korena repozitorijuma, naredbe pokreni redom (svaka može u jednom PowerShell redu):

```sh
python scripts/control_tower.py build --fixture docs/control-tower/fixtures/football-2026-10-10.json --github-fixture docs/control-tower/fixtures/football-github-2026-10-10.json --out docs/control-tower/generated/football-before
python scripts/control_tower.py build --fixture docs/control-tower/fixtures/football-2026-10-10-0950.json --github-fixture docs/control-tower/fixtures/football-github-2026-10-10.json --previous docs/control-tower/generated/football-before/inventory.v1.json --out docs/control-tower/generated/football-2026-10-10
python scripts/control_tower.py diff --before docs/control-tower/generated/football-before/inventory.v1.json --after docs/control-tower/generated/football-2026-10-10/inventory.v1.json --out docs/control-tower/generated/football-observed-diff
python scripts/control_tower.py build --fixture docs/control-tower/fixtures/football-synthetic-before.json --out docs/control-tower/generated/football-synthetic-before
python scripts/control_tower.py build --fixture docs/control-tower/fixtures/football-synthetic-after.json --previous docs/control-tower/generated/football-synthetic-before/inventory.v1.json --out docs/control-tower/generated/football-synthetic-after
python scripts/control_tower.py diff --before docs/control-tower/generated/football-synthetic-before/inventory.v1.json --after docs/control-tower/generated/football-synthetic-after/inventory.v1.json --out docs/control-tower/generated/football-synthetic-diff
uv run --with pytest --with ruff python -m pytest tests/test_control_tower.py -q
```

Opaženi fixture preseci su od 01:47 i 09:50 UTC, 2026-10-10. Sintetički preseci služe samo za proveru diffa. CLI generiše `inventory.v1.json`, `CONTROL_TOWER.md`, `architecture.mmd`, odnosno JSON i Markdown diff. Aktuelni 09:50 presek ima **18/18** registrovanih fudbalskih definicija, **8/18** detaljno mapiranih, **15/18** Git source ref-ova i **8/18** prepoznatih module entrypointa. Samo **4/18** servisa imaju CI run u ograničenom GitHub fixture-u na istom commit SHA; za ostale je veza nepoznata. Broj `RUNNING` instanci, deployment status, uspeh cron ciklusa i svežina podataka su različite stvari.

## Novi read-only capture samo za fudbal

```sh
python scripts/control_tower.py capture-railway --out <local-football-railway.json>
python scripts/control_tower.py capture-github --out <local-football-github.json>
```

Railway komanda koristi samo eksplicitno dozvoljeni project ID i pre zapisivanja proverava odgovoreno ime/ID. Sanitizacija odbacuje varijable, connection string, start komandu, logove, e-mail i deployment meta osim SHA. GitHub čita najviše pet commitova, PR-ova i CI run-ova za jedini dozvoljeni repo; token je opcion i ne upisuje se u izlaz. Nema automatskog osvežavanja, cron posla niti produkcione promene.

`first_seen_at` je najranije vreme u dostupnim snapshotima, ne datum kreiranja. `last_successful_deployment_at` znači da je deployment u nekom preseku imao status `SUCCESS`, ne da je cron posao završen. `cron_last_successful_completion_at` i `data_freshness_at` ostaju `null` bez posebnog dokaza u `--operations-fixture`. Scorecard je ručno obrazložen u `assessment.json`; generator ga ne računa iz metapodataka. Razlog pojedinačne promene u diffu ostaje `reason unknown` dok se ne poveže sa direktnim obrazloženjem.
