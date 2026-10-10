# Registar Railway definicija — snapshot 2026-10-10

Izvor: [sanitizovan Railway status](fixtures/railway-2026-10-10.json), snimljeno `2026-10-10T01:47:58Z`. Svih **48** registrovanih definicija je navedeno (coverage registracije 48/48); potvrđen Git source ref postoji za **31/48**, a prepoznat `python -m` entrypoint za **19/48**. To nisu procenat potvrđene funkcionalne mape ni procenat zdravih servisa. Kategorija iz imena je `inferred` osim PostgreSQL. `first seen` svih je vreme ovog snimka, a stvarni datum kreiranja je `unknown`. Owner nije javno dokumentovan za većinu one-shot definicija. Nema zaključka da je bilo koja bezbedna za brisanje.

| Projekat | Servis / ID | Uloga | Status | Repo @ commit | Entrypoint | Poslednji deployment (UTC) |
| --- | --- | --- | --- | --- | --- | --- |
| believable-contentment | `api-baseball-league-tester`<br>`782d19bd-9567-44f9-8da0-dbbea4928335` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-09-28T18:27 |
| believable-contentment | `api-sports-baseball-query-oneshot`<br>`5939ae20-f221-41b0-b931-bfdd56b7324f` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-09-28T18:27 |
| believable-contentment | `api-sports-game-history-inspection`<br>`b2f2e06e-a663-4bb2-80f1-bc1b4dd14aae` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-10-02T11:28 |
| believable-contentment | `basketball-capability-audit`<br>`5547816d-326f-46ea-89c9-ab5d747261fa` | one-shot/diagnostic (inferred) | scheduled cron; current run unknown | quantbet-baseball @ dc9ac3e0 | `unknown [cron]` | 2026-10-01T12:03 |
| believable-contentment | `basketball-db-audit`<br>`f2447aeb-07b3-43a5-9704-62f7a151c10f` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-10-02T19:05 |
| believable-contentment | `basketball-full-scope-test`<br>`b11fbfcb-ba16-4e77-a2ad-e795a7608091` | one-shot/diagnostic (inferred) | stopped/one-shot | quantbet-basketball @ 4d14ec00 | `compileall` | 2026-10-03T08:14 |
| believable-contentment | `basketball-v2-cold-storage`<br>`5f570c16-e9bd-4f01-bb41-af27afadcbc0` | archive/storage (inferred) | scheduled cron; current run unknown | quantbet-basketball @ d07943ef | `quantbet_basketball_v2.cold_storage [cron]` | 2026-10-04T23:58 |
| believable-contentment | `basketball-v2-dashboard`<br>`41b3eecf-41b6-4a8a-ae8e-2275d200707d` | UI/API (inferred) | running instance | quantbet-basketball @ 41515332 | `unknown` | 2026-10-10T01:21 |
| believable-contentment | `basketball-v2-worker`<br>`2ff0c29b-90ab-4196-a84a-237cd6682697` | worker (inferred) | scheduled cron; current run unknown | quantbet-basketball @ 07f35f0b | `quantbet_basketball_v2.worker [cron]` | 2026-10-10T01:20 |
| believable-contentment | `db-audit-sync`<br>`8d287f9e-3f29-43e9-8af5-fa07db65a256` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-09-28T18:27 |
| believable-contentment | `db-read-only-audit`<br>`084f11b3-9eba-4f88-b12b-5feea6bbd146` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-09-29T01:50 |
| believable-contentment | `fixture-diagnostics`<br>`bb15e429-18e9-4623-b2b1-5b631af666ab` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-09-28T18:27 |
| believable-contentment | `inspect-accepted-picks-v2`<br>`9316fd76-b624-4212-b237-bff9a67c0230` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-09-28T18:27 |
| believable-contentment | `inspect-picks-query`<br>`fc94044e-2086-4855-a3a5-6c5b00a41180` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-09-28T18:27 |
| believable-contentment | `mlb-fixture-diagnostic-query`<br>`d1f766a8-5a81-4ef4-896e-1f4794e20cd6` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-09-29T01:52 |
| believable-contentment | `Postgres`<br>`5318bb44-6df4-4405-a486-4a370e937120` | DB (verified type) | running instance | unknown | `unknown` | 2026-09-28T18:27 |
| believable-contentment | `postgres-audit-runner`<br>`5f7c00da-028f-4f48-8621-dc822b94e131` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-09-28T18:27 |
| believable-contentment | `quantbet-baseball`<br>`e6f5221e-0165-4bb6-9daf-9525ae8ebc5f` | worker (inferred) | scheduled cron; current run unknown | quantbet-baseball @ ed2e1c4f | `quantbot.baseball.worker [cron]` | 2026-09-29T16:53 |
| believable-contentment | `quantbet-baseball-cold-archive`<br>`f05c08ad-91f8-49f9-80d3-75aeae057e63` | archive/storage (inferred) | stopped/one-shot | quantbet-baseball @ b0291228 | `unknown` | 2026-09-29T07:24 |
| believable-contentment | `quantbet-baseball-cold-storage`<br>`a4a98e6d-1e57-45f9-8e32-bafd8bfcf81c` | archive/storage (inferred) | scheduled cron; current run unknown | quantbet-baseball @ 53ff825a | `quantbot.baseball.cold_storage [cron]` | 2026-09-29T07:29 |
| believable-contentment | `quantbet-baseball-dashboard`<br>`3c73f36a-7ab3-479b-9726-c26a81996728` | UI/API (inferred) | sleeping; instance metadata differs | quantbet-baseball @ ed2e1c4f | `quantbot.baseball.dashboard_entrypoint` | 2026-09-29T16:53 |
| believable-contentment | `quantbet-basketball`<br>`1f8ea12c-4b3c-48d5-97c3-d80420035ce2` | worker (inferred) | scheduled cron; current run unknown | quantbet-baseball @ ed2e1c4f | `quantbot.basketball.worker [cron]` | 2026-10-01T12:03 |
| believable-contentment | `quantbet-basketball-backfill`<br>`a2112c60-04ae-453e-ab69-5a535ff1d13d` | worker (inferred) | scheduled cron; current run unknown | quantbet-basketball @ 4987bbc2 | `quantbet_basketball.research_worker [cron]` | 2026-10-05T00:57 |
| believable-contentment | `quantbet-basketball-cold-storage`<br>`4f51e968-76c0-4721-be49-2154b807ad35` | archive/storage (inferred) | scheduled cron; current run unknown | quantbet-basketball @ dd6e8bb4 | `quantbet_basketball.cold_storage [cron]` | 2026-10-03T18:03 |
| believable-contentment | `quantbet-basketball-dashboard`<br>`f20c5f5a-fabb-4a27-9cbd-09437b7180fb` | UI/API (inferred) | sleeping; instance metadata differs | quantbet-basketball @ 4987bbc2 | `unknown` | 2026-10-03T20:56 |
| believable-contentment | `quantbet-basketball-main`<br>`5e144e5a-b28d-4a9b-828a-19102ecaa130` | worker (inferred) | scheduled cron; current run unknown | quantbet-basketball @ 4987bbc2 | `unknown [cron]` | 2026-10-05T00:56 |
| believable-contentment | `quantbet-basketball-ops`<br>`0ef18343-5194-477e-ab89-6e4d68a0f8d0` | worker (inferred) | stopped/one-shot | quantbet-basketball @ 4987bbc2 | `quantbet_basketball.research_worker` | 2026-10-03T20:56 |
| believable-contentment | `quantbet-basketball-research`<br>`208ccc65-9c8a-49eb-a079-934b51f9987d` | worker (inferred) | scheduled cron; current run unknown | quantbet-basketball @ 4987bbc2 | `quantbet_basketball.research_worker [cron]` | 2026-10-05T00:57 |
| believable-contentment | `quantbet-postgres-audit`<br>`7270d59d-d593-4bf1-a870-2b65c6a4f4ed` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-09-28T18:27 |
| believable-contentment | `query-production-db`<br>`0bec39bd-a815-410d-b3d3-fcd67cb4c88e` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-10-05T22:58 |
| sincere-balance | `goallab-void-26a813a9b6`<br>`055d5dd9-f8d6-443c-86e1-67b80357417c` | one-shot/diagnostic (inferred) | stopped/one-shot | v2quantbet @ 6b937536 | `unknown` | 2026-09-29T00:59 |
| sincere-balance | `Postgres`<br>`8053c62b-2ba3-46e8-8bf0-bc5160cb6b9b` | DB (verified type) | running instance | unknown | `unknown` | 2026-09-28T18:27 |
| sincere-balance | `quantbet-archive-lifecycle`<br>`fdb9a387-01ca-45c7-905e-bc7287ea97d4` | archive/storage (inferred) | scheduled cron; current run unknown | v2quantbet @ 39226ad5 | `h2h.archive.lifecycle_entrypoint [cron]` | 2026-10-09T21:07 |
| sincere-balance | `quantbet-dashboard`<br>`69a60980-686b-4156-a615-28b08ffd62c8` | UI/API (inferred) | running instance | v2quantbet @ 8352f01a | `unknown` | 2026-10-10T00:46 |
| sincere-balance | `quantbet-engine`<br>`3204398e-f9cc-49f7-8923-03e054cde348` | worker (inferred) | running instance | v2quantbet @ 8352f01a | `h2h.entrypoint` | 2026-10-10T00:46 |
| sincere-balance | `quantbet-find-26a813a9b6`<br>`9cd6573b-60bc-460b-850c-4e5dbf6755d8` | one-shot/diagnostic (inferred) | stopped/one-shot | v2quantbet @ c6a54e23 | `h2h.archive.entrypoint` | 2026-10-09T23:38 |
| sincere-balance | `quantbet-find2-26a813a9b6`<br>`d963a123-144d-4c05-80ee-f3e3a4a5e704` | one-shot/diagnostic (inferred) | stopped/one-shot | v2quantbet @ 6b937536 | `unknown` | 2026-09-29T00:59 |
| sincere-balance | `quantbet-kelly-tournament`<br>`222072a1-56b3-4679-a61c-e30437ad70a0` | unknown | running instance | unknown | `unknown` | 2026-10-10T01:05 |
| sincere-balance | `quantbet-kellylab`<br>`15a796eb-81b0-4b92-bd1a-c65b7272334d` | UI/API (inferred) | running instance | v2quantbet @ 8352f01a | `h2h.kellylab_dashboard_entrypoint` | 2026-10-10T00:45 |
| sincere-balance | `quantbet-quantlab`<br>`34662406-0e2b-448e-8bee-d8936d1e9998` | UI/API (inferred) | running instance | v2quantbet @ 34a52225 | `h2h.quantlab_dashboard_entrypoint` | 2026-10-10T00:38 |
| sincere-balance | `quantbet-quantlab-collector`<br>`349ad868-2b0a-4192-a530-f9586dea202f` | collector (inferred) | scheduled cron; current run unknown | v2quantbet @ 34a52225 | `h2h.quantlab.collector_entrypoint [cron]` | 2026-10-10T00:38 |
| sincere-balance | `quantbet-quantlab-collector-ACut`<br>`e0923ec8-22be-4d70-8f56-4aefc7add00b` | collector (inferred) | scheduled cron; current run unknown | v2quantbet @ 886af1ce | `unknown [cron]` | 2026-10-04T02:05 |
| sincere-balance | `quantbet-quantlab-modeler`<br>`793608ac-2f9f-4cb1-b28c-a77f78a03a15` | modeler (inferred) | scheduled cron; current run unknown | v2quantbet @ 34a52225 | `h2h.quantlab.modeler_entrypoint [cron]` | 2026-10-10T00:38 |
| sincere-balance | `quantbet-research`<br>`2965d3a3-49d1-4b16-a508-1becb6a9e3e1` | UI/API (inferred) | running instance | v2quantbet @ 8352f01a | `h2h.research_dashboard_entrypoint` | 2026-10-10T00:45 |
| sincere-balance | `quantbet-void-1636701`<br>`7845d562-640c-457a-9569-daf173e001a2` | one-shot/diagnostic (inferred) | failed latest deployment | v2quantbet @ a077d61c | `unknown` | 2026-10-01T23:46 |
| sincere-balance | `quantbet-void-1636701-ops`<br>`9b6e43d2-5305-4c9f-bfee-6db8c5aa6fa1` | one-shot/diagnostic (inferred) | stopped/one-shot | v2quantbet @ a3b26b4e | `unknown` | 2026-10-01T23:52 |
| sincere-balance | `south-america-performance-query`<br>`8d932c12-0b39-45db-9547-6fe2e72c751a` | one-shot/diagnostic (inferred) | stopped/one-shot | unknown | `unknown` | 2026-10-10T00:30 |
| sincere-balance | `south-america-performance-query-v2`<br>`eb56e80e-fc92-49b3-9671-1340a5b15f86` | one-shot/diagnostic (inferred) | stopped/one-shot | v2quantbet @ 24366529 | `unknown` | 2026-10-02T22:50 |

## Tumačenje

- Railway `latestDeployment.status=SUCCESS` znači uspešan poslednji deployment, uključujući završeni jednokratni posao; nije uptime metrika.
- `running_instances` potiče iz Railway instance metapodataka u trenutku snimka. Cron servis između pokretanja očekivano može imati nula `RUNNING` instanci.
- `entrypoint_module=unknown` ne znači da nema start komande: sanitizacija namerno odbacuje inline kod, shell skripte i base64 payload.
- `source_repo=unknown` uključuje PostgreSQL i Railway inline/one-shot servise; ne znači da kod ne postoji.
- Owner, DB role, tabela read/write, provider quota i stvarna data freshness nisu potvrđeni ovim API presekom. Granice aplikacija su opisane u [auditu](ARCHITECTURE_AUDIT_2026-10.md).
