# Application composition

The application composition root is `h2h.application`.

`build_sqlite_quote_service(database_path)` creates a `SQLiteQuoteRepository` and injects it into `QuoteIngestionService`.

This keeps infrastructure selection outside the use-case layer. The use case depends only on the repository contract, while the composition root selects SQLite for a concrete deployment.

The returned service owns the repository reference for its lifetime. Callers that need to release the SQLite connection should retain the repository explicitly or extend the composition root with an application lifecycle wrapper before production deployment.
