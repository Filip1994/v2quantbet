# QuantBet Control Tower V1

Control Tower je mali **offline, read-only** CLI. Ne pokreće novi servis, ne čita DB redove, ne menja Railway/GitHub konfiguraciju i ne utiče na betting odluke. [Arhitektonski audit](ARCHITECTURE_AUDIT_2026-10.md) je istorijski Phase A pregled; [generisani prikaz](generated/2026-10-10/CONTROL_TOWER.md) je obnovljiv iz sanitizovanih ulaza.

## Ponovi rezultat bez naloga ili tokena

Iz korena `v2quantbet` repozitorijuma:

```sh
python scripts/control_tower.py build \
  --fixture docs/control-tower/fixtures/railway-2026-10-10.json \
  --github-fixture docs/control-tower/fixtures/github-2026-10-10.json \
  --out <local-before-directory>
python scripts/control_tower.py build \
  --fixture docs/control-tower/fixtures/railway-2026-10-10-0950.json \
  --github-fixture docs/control-tower/fixtures/github-2026-10-10.json \
  --previous <local-before-directory>/inventory.v1.json \
  --out docs/control-tower/generated/2026-10-10
python scripts/control_tower.py diff \
  --before <local-before-directory>/inventory.v1.json \
  --after docs/control-tower/generated/2026-10-10/inventory.v1.json \
  --out docs/control-tower/generated/observed-diff

python scripts/control_tower.py build \
  --fixture docs/control-tower/fixtures/synthetic-before.json \
  --out docs/control-tower/generated/synthetic-before
python scripts/control_tower.py build \
  --fixture docs/control-tower/fixtures/synthetic-after.json \
  --previous docs/control-tower/generated/synthetic-before/inventory.v1.json \
  --out docs/control-tower/generated/synthetic-after
python scripts/control_tower.py diff \
  --before docs/control-tower/generated/synthetic-before/inventory.v1.json \
  --after docs/control-tower/generated/synthetic-after/inventory.v1.json \
  --out docs/control-tower/generated/synthetic-diff

python -m pytest tests/test_control_tower.py -q
```

Na Windows PowerShell-u možeš staviti svaku komandu na jedan red umesto `\` nastavka. Zameni `<local-before-directory>` lokalnom putanjom. `build` piše `inventory.v1.json`, `CONTROL_TOWER.md` i `architecture.mmd`. `diff` piše `snapshot_diff.v1.json` i `SNAPSHOT_DIFF.md`. Dva Railway fixture fajla su opažena metadata preseka od 01:47 i 09:50 UTC; [njihov diff](generated/observed-diff/SNAPSHOT_DIFF.md) prikazuje stvarne promene statusa. Sintetički pre/posle snapshoti služe samo kao test; nisu istorijski Railway podaci.

Za kasniji stvarni snapshot rezultat je **48/48 definicija u registru**, **20/48 detaljno mapiranih** prema strožem kriterijumu (vlasnik + svrha + dokaz + postojeći kodni put), **31/48 Git source ref** i **19/48 prepoznatih module entrypointa**. Preostalih 28 je vidljivo označeno `unmapped`; to uključuje deo namerno kratkotrajnih servisa i dve DB definicije koje nemaju kodni entrypoint. Dvanaest servisa imalo je `RUNNING` instancu u tom trenutku; dva poslednja deployment statusa bila su `FAILED` ili `CRASHED`. Ovi brojevi nisu procenat dostupnosti ili pouzdanosti sistema.

GitHub metapodaci za `quantbet-basketball` nisu vraćeni u trenutku ovog capture-a (`unavailable:HTTPError`); lokalni Git commit i Railway source ref su pregledani nezavisno. Zato je CI status za taj repo u generisanom prikazu `unknown` gde nema istog commit SHA iz dostupnog GitHub fixture-a.

Primer iz sintetičkog diffa: dodat je jedan ID, `quantbet-engine` je promenio commit i poslednji deployment `SUCCESS → FAILED`, a dokumentovani razlog je `reason unknown`. Odsustvo servisa u kasnijem snapshotu znači samo da nije vraćen u tom preseku.

## Novi read-only snapshot, samo kada vlasnik zatraži osvežavanje

```sh
python scripts/control_tower.py capture-railway \
  --project <football-project-id> --project <sports-project-id> \
  --environment production --out <local-sanitized-railway.json>

python scripts/control_tower.py capture-github \
  --repo Filip1994/v2quantbet --repo Filip1994/h2h \
  --repo Filip1994/quantbet-baseball --repo Filip1994/quantbet-basketball \
  --out <local-sanitized-github.json>
```

`capture-railway` zove samo `railway status --json` za eksplicitno navedene projekte (najviše osam), sa timeoutom. Čuva samo identitet servisa, repo/SHA, prepoznati module entrypoint, cron i poslednji deployment/instance status. Start komanda, inline kod, environment varijable, konekcije, logovi i e-mail se odbacuju. `capture-github` čita najviše pet commitova, pet PR-ova i pet CI run-ova po repozitorijumu (najviše osam), bez PR body-ja, e-maila i tajni. `GITHUB_TOKEN` je opcion za privatni/ograničeni pristup i ne upisuje se u izlaz. Ako je API nedostupan, repo dobija `unavailable:<error type>` i izveštaj ostaje upotrebljiv. Ne postoji automatsko osvežavanje, billing promena ni cron.

## Kako se čita registar

- `first_seen_at` je vreme prvog dostupnog snapshot-a za stabilni Railway ID. Prosledi prethodni registar kroz `--previous` pri svakom osvežavanju; tada se najranije opažanje zadržava. Bez prethodnog registra istorija nije poznata. Ovo **nije** stvarni datum kreiranja; `created_at=null` znači nepoznato.
- `last_changed_at` je vreme poslednjeg Railway deploymenta; promena konfiguracije bez deploymenta nije obuhvaćena.
- `last_successful_deployment_at` zadržava deployment koji je u nekom snapshot-u imao status `SUCCESS`; `last_successful_deployment_observed_at` beleži kada je taj status viđen. Isti deployment može kasnije preći u `CRASHED`, kao kod cold storage servisa, pa ovo nije dokaz novog, zasebnog uspešnog deploy-a ni uspešno završenog cron posla. Ako prethodni registar nije sačuvan, stariji uspeh ostaje nepoznat.
- `cron_scheduled`, `cron_running_now`, `cron_last_successful_completion_at` i `data_freshness_at` su odvojena polja. Poslednja dva ostaju `null` bez direktnog dokaza o završenom poslu odnosno proverene svežine podataka. Opcioni `--operations-fixture` prima takve proverene vremenske oznake i izvore. Nula trenutno aktivnih cron instanci ne dokazuje kvar.
- Scorecard se **ne računa automatski**. Ocene su ručno unete u `assessment.json` prema rubrici, dokazima i nivou pouzdanosti; generator ih samo prikazuje. Budući razlog konkretne promene treba vezati za PR obrazloženje ili odluku, ne za commit naslov.
- `verification=inferred` znači da kod/dokument opisuju namenu, ali nema potvrde stvarnog izvršavanja i DB privilegija. `unknown` se ne pretvara u negativnu ocenu.
- `documented_reason` u registru objašnjava postojeći dizajn samo kada postoji dokument. Snapshot diff za konkretnu promenu uvek kaže `reason unknown` dok ne postoji dokaz koji direktno vezuje tu promenu za PR/odluku.
- `ci_status` se vezuje za isti commit SHA kada je dostupan GitHub fixture. To nije dokaz da je deployment prošao kontrolu.
- `datastores_read/write` su kodno/dokumentaciona mapa. Stvarni PostgreSQL grantovi nisu provereni.

Za operativnu trijažu koristi [runbook](RUNBOOK.md). Za ocene i slepe tačke vidi [audit](ARCHITECTURE_AUDIT_2026-10.md). Pri svakoj budućoj promeni registra pregledati diff, zahtevati direktan dokaz za razlog promene i držati generisani snapshot uz datum i izvorni SHA.

[Ciljane read-only provere](FOLLOWUP_2026-10-10.md) sadrže proveru DB kredencijala, PITR/HA, dijagnostičkih definicija i cron logova. Njihovi nalazi su zaseban, kasniji presek od generisanog registra.
