# Retry policy

`RetryingJsonTransport` wraps the provider-neutral `JsonTransport` boundary.

## Behavior

- `max_attempts` includes the initial request and must be at least `1`.
- `TransportError` and `TransportTimeoutError` are retried.
- `TransportResponseError` is not retried because it represents an invalid or non-retryable provider response.
- Backoff is exponential: `backoff_seconds * 2 ** attempt`.
- A sleeper is injected for deterministic tests; production uses `time.sleep`.
- After the final failed attempt, the last transport error is re-raised.

The retry layer contains no provider-specific logic and does not alter canonical quote or snapshot behavior.
