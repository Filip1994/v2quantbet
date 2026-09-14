# Provider HTTP transport

`h2h.odds.http` isolates network I/O from provider-specific response mapping.

## Contract

`JsonTransport.get_json()` accepts a URL, optional headers, and an explicit positive timeout. It returns a JSON object represented as a mapping.

The stdlib implementation is `UrllibJsonTransport`; it has no third-party dependency.

## Error semantics

- `TransportTimeoutError`: request exceeded the timeout.
- `TransportResponseError`: non-success HTTP response, invalid JSON, or a JSON value that is not an object.
- `TransportError`: other URL/transport failures.

Provider adapters should depend on the `JsonTransport` protocol and should not call `urllib` directly. Tests can inject a fake transport, so no real network access is required.

Retries are intentionally not hidden inside the transport. A later policy layer should own retry count, backoff, and retryable-status decisions.
