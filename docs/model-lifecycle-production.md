# Production Dixon-Coles model lifecycle

The production scheduler owns an independent `model_lifecycle` job. Discovery
materializes required `(provider, team_id_namespace, league_id, season)` scopes;
opportunity processing never trains a model and never uses fixture failures as
the coverage inventory.

## Training policy

- History window: 730 days, half-open, ending at 00:00 UTC on the cycle day.
- Completed results: exact API-Football league and training season, status `FT`,
  ordinary full-time scores only.
- Season handling: try the target season, then at most one previous season. The
  artifact records the training season while its explicit target scope records
  the fixture season.
- Minimum sample: 80 accepted/fitted matches and at least three appearances for
  every provider team required by a future discovered fixture.
- Dixon-Coles parameters: `xi=0.0018`, `ridge=0.01`.
- Freshness: an active pointer becomes stale after 14 days. The old immutable
  version remains usable while a replacement is trained.
- Reference time: the exclusive history-window end; every fitted match is older
  than this UTC timestamp.

All values are validated environment configuration. The complete policy is
SHA-256 fingerprinted and embedded in `trainer_code_version`, so every artifact
provenance record identifies all decision-affecting production policy values.

## Bounds and request safety

One cycle claims at most one scope, permits at most two provider attempts, and
has a 45-second cooperative wall budget. The persistent daily training allowance
is 25 attempted HTTP requests. Training also stops before consuming the final
500 calls of effective operational capacity; the separate global provider
reserve remains unchanged. Every actual retry is counted in PostgreSQL under one
of `discovery`, `model_training`, `opportunity_odds`, or `results_monitoring`.

Strictly validated raw historical responses are cached by exact league, season,
and time window. A restart reuses completed acquisition state rather than
replaying the provider request. Model artifacts are immutable and activation is
an idempotent compare-and-swap; previous versions and predictions remain valid.

## Activation gate

Activation requires a decodable, internally consistent artifact for the target
scope; the configured minimum fitted count; finite objective and parameters;
minimum coverage for every intended team; successful expected-goal, score-matrix
and canonical market probability generation; normalized finite probabilities;
and a matching immutable version ID. Failure records a scope-level status and
never changes the active pointer.
