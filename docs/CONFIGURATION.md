# Configuration boundary

The quote application loads infrastructure configuration through `h2h.config.load_settings()`.

## Required environment

- `API_FOOTBALL_KEY` — required provider credential. It must be non-blank.
- `DATABASE_URL` — required for the production PostgreSQL deployment. It must point to the Railway PostgreSQL service (or another PostgreSQL instance).

## Legacy/test-only environment

- `QUANTBET_DATABASE_PATH` — legacy SQLite path retained temporarily for isolated legacy tests and migration work. It is **not** a production fallback and must not be used by the Railway deployment.

## Example

```bash
export API_FOOTBALL_KEY="<secret-from-secret-manager>"
export DATABASE_URL="<postgresql-connection-string-from-railway>"
```

## Production composition

The production fixture universe is date-window driven and filtered by
`ScopedFixtureDiscovery` through the fail-closed Phase I competition policy.
It does not accept a league/season or fixture-ID allowlist. The production
opportunity scheduler keeps `QUANTBET_BOOKMAKER_ID` as its legacy cadence anchor, while
execution always uses the hard-approved Bet365/1xBet/Superbet universe. The former
`QUANTBET_PILOT_SCOPES`, `QUANTBET_PILOT_FIXTURE_IDS`, and
`QUANTBET_PILOT_BOOKMAKER_ID` names are not part of the production contract.

`QUANTBET_API_FOOTBALL_PUBLISHED_MAX_AGE_SECONDS` defaults to **36000 (10 hours)**.
Production compares the provider's last update timestamp with this limit in both
preliminary evaluation and mandatory targeted final quote verification. A recent
local capture does not reset the provider age. The final request must still return
a complete market for the same bookmaker and market before a pick can be registered.

Opportunity logs distinguish `PROVIDER_RESPONSE_EMPTY` (no provider response
records), `NO_SUPPORTED_CANONICAL_QUOTES` (records but no supported normalized
quotes), `NO_COMPLETE_SUPPORTED_MARKET` (quotes but no complete two-way market),
and `PERSISTED_MARKET_OUTSIDE_PROVIDER_AGE` (persisted complete market older than
the configured provider-age limit). They include `provider_response_items` and
`canonical_quote_count` when available. Final verification logs also report a
specific `odds_unavailable_reason` alongside the durable `rejection_reasons`.

```python
from h2h.application import build_postgres_quote_history_application_from_settings
from h2h.config import load_settings

settings = load_settings()
with build_postgres_quote_history_application_from_settings(settings) as application:
    quotes = application.service.read_all()
```

The production path is PostgreSQL. The application must fail clearly when `DATABASE_URL` is missing rather than silently creating or selecting a local SQLite database.

Secrets are not included in the `repr()` output of `ApplicationSettings`. Tests use synthetic credentials only; no real provider key belongs in source control.

## Task #10 registration policy

Pick registration uses a complete, validated policy loaded by
`load_registration_policy_config()`. The initial pilot values are represented
explicitly by the `QUANTBET_*` variables in `.env.example`; monetary values use
integer minor RSD units. Partial configuration fails closed, and the canonical
non-secret configuration is fingerprinted and persisted with every decision.

`QUANTBET_ALLOWED_FIXTURE_STATUSES` has no default. Fixture status is currently
an opaque API-Football provider value, so deployment must supply the exact
operationally approved pre-match statuses instead of relying on an invented
domain interpretation.

Application composition does not create or fund the bankroll. Deployment/test
setup must invoke the explicit idempotent `BootstrapBankroll` operation once for
the configured account before eligible registrations can reserve stake.

## Task #11 monitoring and Bulletin

Pick monitoring requires the complete explicit set
`QUANTBET_PICK_MONITOR_INTERVAL_SECONDS`, `QUANTBET_CURRENT_MAX_AGE_SECONDS`, and
`QUANTBET_CLOSING_MAX_AGE_SECONDS`. Each must be a positive integer number of seconds; partial
configuration fails closed. The values and `ODDS_LIFECYCLE_V1` are pinned when a pick enters
`MONITORING`.

`QUANTBET_BULLETIN_TIMEZONE` must be a valid IANA timezone. It defaults to the approved V1
timezone `Europe/Belgrade`; it never uses the host's local timezone implicitly.
