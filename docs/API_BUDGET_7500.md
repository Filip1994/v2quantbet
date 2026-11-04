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
normal interval (300 seconds in production), while monitoring and results wait
at least 60 seconds after a slice completes. A nonempty backlog therefore cannot
re-run these workers every five-second scheduler tick. Results remain bounded to
two fixtures per slice. Settlement rules and fixture identity checks are intact.

The API provider's already-used daily allowance cannot be restored by this
change. At the November 5 rollout (Belgrade), November 4 UTC usage was already
above 7,500; calls resume only after the UTC day changes (01:00 in Belgrade in
winter). A complete later day is required to measure normal consumption.
