# Predlog: merge dokumentacije bez automatskog Railway deploymenta

**Status: predlog za zasebno odobrenje; konfiguracija nije primenjena.** PR #244 ostaje draft i ne spaja se dok vlasnik ne potvrdi release postupak.

## Dokaz uzroka

PR #243 je u `main` uneo samo četiri fajla pod `docs/control-tower/` ([merge commit `4842946`](https://github.com/Filip1994/v2quantbet/commit/48429464389259c65415ef7195d5819b1632379f)). Railway deployment `f7780cc5-37d8-4c94-b97f-2c80afc01c69` za `quantbet-kellylab` nastao je 2026-10-10 u 11:58:07 UTC iz istog SHA i završio `SUCCESS`. Njegova konfiguracija povezuje `Filip1994/v2quantbet@main`, nema `watchPaths`, ima `checkSuites=false` i predeploy `python -m h2h.migrate`. Log je u 11:58:25 UTC zabeležio `applied 0 migration(s)`: komanda je izvršena i nije primenila novu migraciju u tom pokretanju. To ne dokazuje da su svi servisi ili DB podaci ostali neizmenjeni.

Read-only pregled svih 15 GitHub povezanih definicija u `sincere-balance` pokazao je 14 na `main` i jednu na `ops/void-1636701`; nijedna od tih konfiguracija ne navodi `watchPaths`, a `checkSuites=false` je svuda gde je prikazan. Osam `main` servisa ima `python -m h2h.migrate` kao predeploy: engine, research, QuantLab dashboard, collector, collector-ACut, modeler, KellyLab i archive lifecycle. Svaki novi commit na povezanoj grani zato predstavlja potencijalni deployment okidač; istorija #243 potvrđuje okidač za KellyLab, ne za svaki servis pojedinačno. Railway [autodeploy dokumentacija](https://docs.railway.com/deployments/github-autodeploys) kaže da povezani servisi automatski deploy-uju nove commitove na izabranoj grani. [Watch paths](https://docs.railway.com/builds/build-configuration#configure-watch-paths) preskaču deployment kada promenjeni fajlovi ne odgovaraju obrascima.

GitHub workflow `.github/workflows/ci.yml` ima `push: main` i `pull_request` bez path filtera. GitHub CI path filter utiče samo na pokretanje CI-ja; ne zaustavlja Railway GitHub vezu. `Wait for CI` bi dodao uslov za rezultat testa, ali ne bi preskočio uspešan dokumentacioni commit. Ne treba menjati CI filter kao rešenje za ovaj incident.

## Najmanji predloženi zahvat

Za svaki od 14 produkcionih servisa povezanih sa `v2quantbet@main`, zasebno podesiti Railway **Watch Paths** sa pozitivnim obrascima za stvarne runtime/build ulaze. Predloženi početni skup koji treba pregledati po servisu:

```gitignore
/src/**
/migrations/**
/pyproject.toml
/uv.lock
/.python-version
/Dockerfile
/railway*.json
```

Ovo obuhvata aplikacioni kod, SQL migracije, zavisnosti, Python verziju i build/deploy konfiguraciju iz trenutnog repozitorijuma; `docs/control-tower/**`, `.github/**`, testovi i offline `scripts/control_tower.py` nisu okidači. Pre primene treba proveriti za svaki servis da li koristi dodatni runtime ulaz, na primer konkretan skript, konfiguracioni ili asset fajl, i uključiti ga. Pozitivni obrasci namerno zahtevaju taj pregled: propušten runtime fajl bi preskočio potreban deployment. Railway obrasci se ocenjuju od korena repozitorijuma čak i uz Root Directory.

Redosled posle **izričitog odobrenja**: (1) zabeležiti trenutnu konfiguraciju i poslednji uspešni deployment/commit svakog servisa, (2) primeniti pregledane watch paths, prvo na jednom neključnom povezanom servisu, (3) proveriti Railway pending promene i ne izazivati nepotreban deploy, (4) potvrditi ponašanje kontrolisanim dokumentacionim commitom i potom runtime commitom uz planiran release, (5) postepeno proširiti na ostale servise, (6) tek zatim razmotriti merge #244. Ako validan runtime commit bude preskočen, vratiti prethodne obrasce ili ukloniti filter za taj servis i ručno deploy-ovati tačan pregledani commit uz odobrenje. Povratak na prazne watch paths vraća širok autodeploy rizik.

Alternativa za strožu kontrolu release-a je posebna produkciona grana ili isključenje autodeploya uz ručni deployment. To je veća promena procesa i zahteva zaseban operativni dogovor. Nikakav Railway config, webhook, branch, deploy ili DB nije promenjen ovim predlogom.
