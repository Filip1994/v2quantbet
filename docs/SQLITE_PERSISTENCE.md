# SQLite persistence

`SQLiteQuoteRepository` provides a database-backed implementation of the provider-neutral `QuoteRepository` contract.

## Guarantees

- Stores canonical quotes using a primary key of `(fixture_id, bookmaker_id, market, selection)`.
- Repeated identical observations are idempotent.
- A different observation for an existing identity raises `QuoteConflictError`.
- `save()` is atomic: a conflict rolls back all writes from that call.
- `all()` and `for_fixture()` reconstruct immutable `CanonicalQuote` objects and preserve insertion order.
- Uses only Python's standard-library `sqlite3` module.

## Usage

```python
from h2h.persistence import SQLiteQuoteRepository

repository = SQLiteQuoteRepository("quotes.sqlite")
repository.save(quotes)
fixture_quotes = repository.for_fixture("fixture-1")
repository.close()
```

The repository creates the `quotes` table automatically when initialized. The caller is responsible for closing the repository.
