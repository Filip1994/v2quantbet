# Application composition

The application composition root is `h2h.application`.

## Production path: PostgreSQL

The Railway deployment must use PostgreSQL. Build the application from validated settings:

```python
from h2h.application import build_postgres_quote_history_application_from_settings
from h2h.config import load_settings

settings = load_settings()
with build_postgres_quote_history_application_from_settings(settings) as application:
    quotes = application.service.read_all()
```

This composition path requires `DATABASE_URL`. If it is missing, composition fails explicitly instead of falling back to a local database.

`PostgreSQLQuoteHistoryApplication` exposes the migration hook and an explicit lifecycle boundary. Repository connections are opened per operation, so `close()` is intentionally a no-op; the context manager remains available for a uniform application lifecycle.

## SQLite status

The SQLite builders and application remain temporarily available only for legacy tests and migration work. They are not an approved production deployment path and must not be selected by Railway runtime code.

This keeps infrastructure selection outside the use-case layer: the use case depends on the repository contract, while the composition root selects PostgreSQL for production.
