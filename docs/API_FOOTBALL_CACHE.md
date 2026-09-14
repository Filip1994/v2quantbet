# API-Football response cache

`ApiFootballClient` supports an optional in-memory cache keyed by `fixture_id`.

- `cache_ttl_seconds=0` disables caching.
- A positive TTL serves the cached payload while it is fresh.
- Expired entries are removed and fetched again.
- `clear_cache()` invalidates all cached fixture responses.

The cache is process-local and is not a replacement for durable persistence. It is intended to reduce duplicate API calls during one application process and works together with the daily API budget.
