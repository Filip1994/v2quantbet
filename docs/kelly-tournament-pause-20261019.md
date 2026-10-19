# Kelly Tournament pause

Explicit operator request: suspend the entire Kelly Tournament universe to reduce
costs while flat staking stabilizes. On 2026-10-19 at 12:31:15 UTC, stopped the
standalone `quantbet-kelly-tournament` deployment
`8286a94b-0aea-4b87-bddb-82afbb81c240` (service
`222072a1-56b3-4679-a61c-e30437ad70a0`, project `sincere-balance`).
Railway reports REMOVED: this removes the running deployment, not the service,
variables, databases or history. The service has no cron, no Git push trigger,
no attached volumes and no interval-based collection in its source. All
Research/Production tournament routes cease executing with that deployment.

This is a read-only Bun simulation service over KellyLab JSON and PostgreSQL
production picks. It does not own actual settlement processing. The original
KellyLab service, production flat stake, existing positions, bankroll, Kelly
formulas and settlement workers remain unchanged.

Hub marks Tournament PAUZIRANO and removes its link while the Dashboard variable
`QUANTBET_KELLY_TOURNAMENT_PAUSED=true` is set. No disabled service is fetched by
the Hub. Source and full pre-pause non-secret configuration are archived in
`C:/Users/User/Documents/ChatGPT/fudbal/corner-buckets-20261019/`:

* `kelly-tournament-archived.tsx` (decoded original Railway function source).
* `kelly-tournament-before.json` (original source image/start command, service
  configuration, deployment identity, variable names, and domain).

The decoded function is also preserved in `docs/archive/kelly-tournament-20261019.tsx`.
To resume only when requested: redeploy the retained Tournament deployment/image
with its archived start command and retained variables; verify the service;
then unset the Hub pause flag and redeploy Dashboard. Do not reset or restore
the live database. A request to stabilize flat stakes is not automatic permission
to resume the Tournament later.
