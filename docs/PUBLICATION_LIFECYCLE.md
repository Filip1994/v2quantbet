# QuantBet publication lifecycle

Production operates one rolling opportunity system with two output views.

- Discovery maintains the configured future horizon (72 hours initially) without a
  same-calendar-day restriction.
- The opportunity worker runs continuously (normally every 60 seconds). A newly
  qualifying fixture is registered immediately, whether kickoff is today, tomorrow,
  or later inside the horizon.
- A preliminary candidate can never be accepted directly. It must claim a durable
  final-verification identity, consume a normal `opportunity_odds` request, build one
  exact complete market from that response, reprice, and repeat model, kickoff,
  price, duplicate, exposure, and risk validation.
- Provider `observed_at` remains authoritative provenance. If the mandatory pull
  returns the provider's latest complete market with an old `observed_at`, the audit
  records `stale_quote=true`, `STALE_QUOTE_WARNING`, and the exact quote age. Age
  alone is not a final rejection; all other market and safety gates remain hard.
- Every accepted verification records final odds, model probability, de-vig
  probability, edge, EV, and `minimum_playable_odds = (1 + minimum EV) / model
  probability`.
- Registered picks remain the source of truth for deduplication and stake exposure.

The Daily Bulletin runs from 00:10 Europe/Belgrade, with restart catch-up bounded to
06:00. Its deterministic identity is the local date, timezone, and bulletin version.
It is an immutable snapshot of registered picks that are still prematch, unsettled,
and inside the rolling horizon at `as_of`; it is not a filter on `registered_at`.
Therefore the same `pick_id` can appear in later bulletins without creating another
pick, stake reservation, or publication decision.
