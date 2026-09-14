# Configuration boundary

The quote application loads infrastructure configuration through `h2h.config.load_settings()`.

## Required environment

- `API_FOOTBALL_KEY` — required provider credential. It must be non-blank.

## Optional environment

- `QUANTBET_DATABASE_PATH` — SQLite database path. Defaults to `data/quantbet.sqlite3`.

Example:

```bash
export API_FOOTBALL_KEY="<secret-from-secret-manager>"
export QUANTBET_DATABASE_PATH="data/quantbet.sqlite3"
```

## Usage

```python
from h2h.application import build_sqlite_quote_application_from_settings
from h2h.config import load_settings

settings = load_settings()
with build_sqlite_quote_application_from_settings(settings) as application:
    quotes = application.service.read_all()
```

Secrets are not included in the `repr()` output of `ApplicationSettings`. Tests use synthetic credentials only; no real provider key belongs in source control.
