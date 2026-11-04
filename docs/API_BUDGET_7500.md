# Football API daily operating budget

The shared API-Football allowance is 7,500 attempted requests per UTC day across
the engine and CornerLab collector. The existing PostgreSQL budget, advisory
transaction lock, and `provider_request_usage` counters remain authoritative.
Failed attempts count; restarts do not reset usage. Exhausted workers wait for
the next UTC day. No provider observations or pick decisions are reset.

Production settings:

| Setting | Engine / dashboard | CornerLab collector |
| --- | ---: | ---: |
| `QUANTBET_API_DAILY_LIMIT` | 7500 | 7500 |
| `QUANTBET_API_RESERVE` | 0 | 1500 |
| `QUANTBET_MODEL_TRAINING_DAILY_REQUEST_LIMIT` | 500 | unused |
| `QUANTBET_MODEL_TRAINING_OPERATIONAL_RESERVE` | 2000 | unused |

The collector stops when shared usage reaches 6,000, leaving 1,500 for engine
operations. Training can use at most 500 and stops once shared usage reaches
5,500. These allowances are part of the same 7,500 total, not additional quotas.
CornerLab's offline modeler and Research dashboard do not make provider requests.

Backlog processing observes a cooldown: opportunities retain their configured
normal interval (300 seconds in production), while monitoring waits at least
60 seconds after a slice completes.

Engine result acquisition runs once daily at 08:00 Europe/Belgrade (configured
with `QUANTBET_RESULT_COLLECTION_HOUR` and the bulletin timezone). It takes a
snapshot of all due fixtures and processes groups of up to 20 in one provider
request. Each fixture is attempted once in that run; failed or incomplete
results wait for the next daily cycle. The durable worker start timestamp
prevents a restart from repeating that day's cycle, including a failed cycle.
A missed cycle is caught up once when the service returns after its scheduled
hour. The local schedule follows daylight-saving changes.

Settlement rules and fixture identity checks are intact. In particular, a new
terminal result still needs a later matching confirmation: settlement can wait
until the following daily cycle. The CornerLab collector keeps its separate
six-hour collection and statistics/settlement refresh schedule. Its calls share
the same 7,500 total, and reducing engine polling leaves more of it available.

The API provider's already-used daily allowance cannot be restored by this
change. At the November 5 rollout (Belgrade), November 4 UTC usage was already
above 7,500; calls resume only after the UTC day changes (01:00 in Belgrade in
winter). A complete later day is required to measure normal consumption.
