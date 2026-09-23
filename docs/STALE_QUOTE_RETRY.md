# Stale provider quote refresh

Quote freshness and transport recency are separate facts:

- `observed_at` is the provider's observation/update time and remains the
  authoritative quote-age timestamp. A mandatory final pull preserves an old
  value as `STALE_QUOTE_WARNING`; request time and `captured_at` never replace it.
- `captured_at` is when QuantBet first persisted that immutable provider
  observation. Re-fetching the same semantic observation does not rewrite it.
- `last_attempt_at` is operational scheduling state for a provider pull. It
  prevents repeated identical payloads from causing a tight polling loop.

The opportunity scheduler resolves only exact complete two-way observations.
Both selections must have the same market, provider `observed_at`, and source;
selections from different observations are never combined for de-vig.

`production_quote_refresh_states` stores `FRESH`, `STALE`, or
`NO_USABLE_QUOTE` per fixture/bookmaker. A stale response records its first and
latest attempt, attempt count, selected complete-market provenance, and next
retry time. This makes the accelerated path replay- and restart-safe without
overloading generic transport failures.

The default stale policy is an initial 120-second retry, exponential backoff
capped at 900 seconds, at most five stale responses (including the initial
pull), and a 3600-second retry horizon. After the bound, normal kickoff-aware
cadence resumes from the latest actual attempt. Retries stop inside the
configured minimum-to-kickoff window. All requests use the existing
`opportunity_odds` budget category and the existing bounded opportunity slice.
One slot per opportunity cycle is reserved for a due stale retry independently
of the normal kickoff keyset cursor; the remaining slots keep normal backlog
progressing, so neither workload can monopolize the worker.

Configuration:

- `QUANTBET_STALE_QUOTE_INITIAL_RETRY_SECONDS`
- `QUANTBET_STALE_QUOTE_MAX_RETRY_SECONDS`
- `QUANTBET_STALE_QUOTE_MAX_ATTEMPTS`
- `QUANTBET_STALE_QUOTE_RETRY_HORIZON_SECONDS`

These values affect operational scheduling only and do not change the
registration-policy fingerprint. `QUANTBET_MAXIMUM_QUOTE_AGE_SECONDS` is
unchanged and still classifies telemetry/retry state; after the mandatory final
provider pull, quote age alone is no longer an independent acceptance rejection.
All non-age model, market, kickoff, edge, EV, risk, and budget gates remain hard.
