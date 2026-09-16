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
