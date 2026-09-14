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
