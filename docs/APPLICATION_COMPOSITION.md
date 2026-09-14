# Application composition

The application composition root is `h2h.application`.

`build_sqlite_quote_service(database_path)` creates a `SQLiteQuoteRepository` and injects it into `QuoteIngestionService`. It remains available as a simple convenience factory, but it does not expose an application-level lifecycle wrapper.

For production-facing code, prefer `build_sqlite_quote_application(database_path)`. It returns a `SQLiteQuoteApplication` containing both the service and repository and supports explicit cleanup:

```python
from h2h.application import build_sqlite_quote_application

with build_sqlite_quote_application("quotes.sqlite3") as application:
    application.service.read_all()
```

The context manager closes the underlying SQLite connection on exit, including when the managed block raises an exception. Explicit cleanup is also available through `application.close()`.

This keeps infrastructure selection outside the use-case layer. The use case depends only on the repository contract, while the composition root selects SQLite for a concrete deployment.
