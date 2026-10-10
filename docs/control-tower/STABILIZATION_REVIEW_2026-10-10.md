# QuantBet stabilizacija — tehnički pregled, 10. oktobar 2026.

**Aktivni opseg:** isključivo football Railway projekat `sincere-balance`. Read-only Railway, PostgreSQL i GitHub provere; dokumentacija u draft PR #244. Nisu menjani produkciona konfiguracija, podaci, role, grantovi, modeli, betting logika ili servisni rasporedi.

## Potvrđeno / verovatno / nepoznato

| Oblast | Potvrđeno | Zaključak sa ograničenjem |
| --- | --- | --- |
| Collector cron | Ciklus započet 08:01 UTC završio se u 09:49:40 UTC sa `cycle completed`, uključujući 2.182 GoalLab odluke, 2.546 CornerLab odluka, 3 CardLab odluke, 716 H2HLab odluka, 1.000 market fixtures i 2.258 otkrivenih fixtures. Ciklusi 10, 11, 12, 13 i 14 UTC nemaju `cycle completed`; poslednji je `CRASHED` u 14:07:58. | Ne radi se o tome da je cron potpuno isključen: proces počinje. Posle GoalLab `history_loaded rows=30000` nema sledećeg stage loga ni Python traceback-a. |
| Uzrok | Limit kolektora je 750.000.000 bajtova (~0,75 GB); uspešan ciklus dosegao je 0,743 GB, a ciklus u 14 UTC 0,733 GB pri uzorkovanju. Posle istorijskog upita kod gradi obiman scoring context iz 30.000 redova i JSON player payload-a. | **Visoka sumnja na memory kill/OOM**, ali bez Railway exit reason ili kernel OOM događaja to nije dokazan tačan uzrok. Nema dokaza da je docs-only merge ili nova verzija koda izazvala pad: 11–14 UTC deploy zapisi koriste isti SHA `34a52225`. |
| Podaci | U 14:30 UTC `MAX(captured_at)` za `quantlab_market_captures`, `quantlab_fixture_observations` i discovery shards bio je 08:01:22 UTC. Poslednji GoalLab picks, H2H snapshots/decisions i shadow bets takođe imaju 08:01:22 UTC. Corner feature snapshot je 09:47, Card event 08:11 i feature 09:16; to su izlazi dugog uspešnog ciklusa. Goal decisions postoje i kasnije, do 14:06, bez dokaza da je pun ciklus završen. | **Postoji svežinski jaz** u core fixture/market prikupljanju. Ne može se tvrditi trajni gubitak svih podataka: istorijski fixture/statistics backfill postoji u kodu. Tačne vremenske odds slike koje nisu snimljene možda se ne mogu naknadno rekonstruisati. `quantlab_market_observations` ima ~5,46 miliona redova; neindeksirani `MAX(captured_at)` je istekao na read-only upitu, pa je njegova zasebna svežina nepoznata. |
| Modeler | Railway poslednji modeler cron označava `cronSucceeded` u 12:32 UTC; `quantlab_goal_model_versions` ima `trained_at` do 12:19 UTC. | Modeliranje je zaseban proces i nije dokaz da collector prikuplja sveže podatke. |
| GitHub → Railway | 15 GitHub povezanih servisa, 14 na `main`, jedan na ops grani; 14 već imaju `build.watchPatterns`, KellyLab nema. Docs-only #243 merge je pokrenuo KellyLab i predeploy migracioni korak (0 migracija). | Precizan per-service predlog je u [deployment planu](DEPLOYMENT_GUARD_PROPOSAL.md). |
| DB prava | Jedina login rola je `postgres`, sa `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `REPLICATION` i `BYPASSRLS`; ona je vlasnik svih 79 javnih tabela i ima SELECT/INSERT/UPDATE/DELETE/TRUNCATE nad svih 79. Od 17 ne-DB servisa, 16 sa `DATABASE_URL` koristi iste user/password/database vrednosti kao Postgres servis. | Ovo je potvrđen visok blast radius. Kodna granica između Production i QuantLab nije DB security granica. Nije dokazan konkretan neovlašćeni upis. |
| Oporavak | Baza zauzima 19,5 milijardi bajtova (~18,1 GiB; `pg_database_size=19.475.068.607`). PITR `enabled=false`, `bucketWired=false`; HA `isCluster=false`, jedan član. Railway CLI `pitr backup list=[]` i `pitr schedule list=[]`. | Nema potvrđene upotrebljive rezervne kopije ili restore probe. Ove provere ne isključuju volume backup u UI-ju ili spoljašnji `pg_dump`, jer njihov inventar nije bio dostupan kroz korišćeni read-only API. Existing cold archive bucket nije PostgreSQL backup. |

### Collector: klasifikacija kvara i preporuka

1. **Deploy/build:** predeploy završava `applied 0 migration(s)`, proces startuje; nema build/migration greške u pregledanim ciklusima.
2. **Cron:** raspored `0 * * * *` izvršava pokušaje; poslednji ciklus ima `cronFailed`. Nula running replika između ciklusa je normalna, ali više izostalih `cycle completed` jeste incident.
3. **Modeliranje:** odvojeni modeler završava; GoalLab scorer u collector-u postaje usko grlo pre core collection. Nema osnova za promenu modela ili parametara.
4. **Prikupljanje:** poslednji potvrđeni core fixture/market capture 08:01 UTC u read-only preseku 14:30 UTC. Sva četiri laba su završila **jedan** raniji ciklus; nastavak redovnog rada za 10–14 UTC nije potvrđen.

Najmanja operativna mera za zasebno odobrenje: povećati samo collector memory limit sa 750 MB na 1,5 GB, bez promene koda/modela/rasporeda, u planiranom prozoru; pratiti peak RAM, exit reason, `cycle completed`, 4 lab counter-a i nove capture timestampove kroz najmanje dva uzastopna satna ciklusa. Sačuvati prethodnu vrednost i, ako dva ciklusa opet ne završe ili se pokaže neprihvatljiv trošak, vratiti 750 MB u odobrenom rollback prozoru. **Ovo je hipotezom vođena mera, ne dokazani bug fix.** Ako i dalje pada, zaustaviti se i pribaviti exit/OOM reason; zatim dizajnirati streaming istorije uz parity test modelskih izlaza u zasebnom PR-u. Bez pouzdanog dokaza o kodnom bugu nema opravdanja da sada otvorimo code-fix PR.

## Privilegije: predložena matrica odgovornosti

Ovo je **source-level mapa za dizajn grantova**, ne potvrda svake runtime putanje. Sadašnja superuser rola može mnogo više. `schema_migrations` i DDL treba da budu dostupni samo migracionoj roli; osam servisa trenutno pokreće migraciju kao predeploy, uključujući rezervni ACut.

| Grupa servisa | Potrebno čitanje | Potreban upis po kodu | Predlog |
| --- | --- | --- | --- |
| `quantbet-engine` | Production facts, research signals, izabrani QuantLab goal pick/settlement podaci za funnel | `fixtures`, `fixture_observations`, quote/model/decision/pick/settlement/bankroll/worker/funnel tabele, `research_signals`, `provider_request_usage` | `qb_production_rw`, bez DDL i bez upisa u `quantlab_*`. |
| `quantbet-dashboard`, `quantbet-research` | Production, `research_signals`, potrebni QuantLab join podaci | Rutinski dashboard kod je čitalački; predeploy sada ima DDL mogućnost | Posebne read-only runtime role nakon uklanjanja predeploy migracije. |
| `quantbet-quantlab` dashboard | `quantlab_*`, odabrane Production/Research facts | Nema potvrđene rutinske DB write putanje dashboarda; predeploy sada ima DDL mogućnost | Read-only runtime rola, uz proveru svih UI akcija pre grant-a. |
| `quantbet-quantlab-collector` | QuantLab istorija, aktivni Production model, potrebni shared facts i API budget | `quantlab_fixtures`, observations/captures, Goal/Corner/Card/H2H decisions/picks/settlements/snapshots, `provider_request_usage` | `qb_quantlab_rw` nad eksplicitnim QuantLab tabelama + uski shared budget upis; bez Production pick/bankroll upisa. |
| `quantbet-quantlab-modeler` | QuantLab istorija/modeli | `quantlab_goal_model_versions`, validations i `quantlab_corner_model_versions` prema kodnoj putanji | Početno ista QuantLab granica; kasnije odvojiti modeler od collectora tek posle call-graph testa. |
| `quantbet-kellylab` | `research_signals`, rezultati/fixtures potrebni za shadow sync | `kellylab_portfolios`, `kellylab_picks` | Posebna KellyLab rola, bez Production bankroll/pick upisa. |
| `quantbet-archive-lifecycle` | Archive catalog + odabrane QuantLab/Production činjenice | `cold_archive_batches`, `cold_archive_watermarks`; kontrolisani `DELETE` nad `quantlab_market_observations` | Posebna archive rola; retention DELETE je namerna i traži poseban test. |
| Rezervni i dijagnostički servisi | Zavisi od režima, npr. archive audit čita; smoke piše archive catalog | Nije bezbedno dati generičku write rolu po nazivu servisa | Zadržati bez automatskog deploya; vlasnik, konkretan mode i privremeni grant pre svakog korišćenja. |
| Jednokratni migration runner | `schema_migrations`, katalog | DDL/migrations, `schema_migrations` | `qb_migrator` kao jedina privilegovana migraciona rola; bez trajnog runtime credential-a u svim servisima. |

**Redosled migracije prava:** prvo validan backup/restore dokaz; zatim izolovan clone i test grant matrice; izbaciti `python -m h2h.migrate` iz runtime predeploya i zameniti kontrolisanim jednim migracionim korakom u release postupku bez novog stalnog servisa; kreirati ne-superuser role/grantove i sekvence; testirati `has_table_privilege` plus stvarne start/cycle tokove u izolaciji; tek onda planirati rotaciju varijabli po servisu i rollback sa starim credentialom u vremenski ograničenom prozoru. Produkcione role, grantovi i tajne nisu menjani.

## Backup, retention, restore i trošak — predlog

Railway [vodič](https://docs.railway.com/guides/postgres-backups-restores) razlikuje volume snapshots, PITR i prenosivi `pg_dump`. Predlog u fazama, uz posebno odobrenje za svaku operativnu promenu:

1. Proveriti u Railway **Postgres → Backups** da li postoje volume snapshotovi i zabeležiti ID/vreme/retention; pribaviti inventar spoljašnjih dumpova i njihov checksum. Dok toga nema, recovery je **neproveren**.
2. Uključiti postojeću Railway scheduled volume backup opciju: daily (6 dana), weekly (1 mesec), monthly (3 meseca); potvrditi prvi završen snapshot. Ovo nije dovoljan offsite backup: Railway kaže da brisanje volume-a briše i njegove backup-e.
3. Uključiti Railway PITR na postojećem Postgres servisu u odobrenom prozoru; ovo kreira storage bucket i redeployuje DB. Sačekati prvi base backup i proveriti WAL archiver/coverage. PITR prozor počinje tek od prvog novog base backup-a, okvirno 4 nedelje.
4. U odobrenom offline koraku napraviti prenosivi `pg_dump --format=custom --no-owner` sa checksumom i čuvati najmanje 30 dana na zasebnom pristupnom domenu. Postojeći archive bucket se ne proglašava DB backupom; mogućnost njegovog korišćenja traži proveru pristupa i odvajanja retention-a. Ne uvoditi novi stalni scheduler pre dokaza da postojeći operativni proces može pouzdano da pravi dump.
5. **Izolovan restore test:** zaseban privremeni Postgres u izolovanom okruženju, bez produkcionih service varijabli, routinga i API ključeva; import kopije, provera checksum-a, schema migrations, broja ključnih tabela i reprezentativnih vremenskih watermarka; izmeriti vreme do čitljive baze. Nema restore-a u postojeći production Postgres niti promene produkcionih podataka. Posle testa deprovision tek uz odobrenje.

Cilj za usaglašavanje: RPO ≤ 1 h kada je PITR zdrav; volume snapshots sami daju do 24 h; RTO se ne može obećati dok restore nije izmeren. Po [Railway cenama](https://docs.railway.com/pricing/plans) volume/snapshot jedinstveni bajtovi koštaju $0,15/GB-mesec, bucket $0,015/GB-mesec, upload iz servisa $0,05/GB. Na sadašnjih 19,5 milijardi bajtova, **jedna puna dodatna volume kopija** je približno $2,92/mesečno pri decimalnom obračunu GB; inkrementalni dnevni/weekly trošak zavisi od promenjenih bajtova. **18 GB kompresovanog bucket sadržaja** bi bilo $0,27/mesečno plus oko $0,90 za jednokratan 18 GB upload; stvarna PITR veličina, WAL stopa, kompresija, postojeći plan i restore compute nisu izmereni. Privremena restore baza slične veličine nosi približno $2,92 po punom mesecu storage-a plus RAM/CPU za stvarno trajanje; bez vremenskog testa nije moguća tačna cena.

## Redosled odluka

1. Odobriti ili korigovati collector memory-only mitigaciju i njenu dvociklusnu proveru; rizik nizak za betting logiku, srednji za trošak i cron dostupnost.
2. Odobriti per-service watch paths iz [plana](DEPLOYMENT_GUARD_PROPOSAL.md); rizik srednji zbog mogućeg false negative obrasca, uz scenario test i rollback.
3. Potvrditi backup inventar, zatim odobriti volume backup/PITR i izolovan restore; operativni rizik srednji, neodložan zbog sada neproverenog oporavka.
4. Posle restore dokaza revidirati i odobriti DB role/credential split; rizik visok za dostupnost, pa sprovesti po fazama i sa rollbackom.
5. Tek posle zaštite deploymenta zasebno odlučiti o merge-u draft PR #244. Nema opravdanja za promenu betting logike ili nove stalne servise.
