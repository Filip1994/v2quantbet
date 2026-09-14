"""HTTP client boundary for API-Football odds data."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from urllib.parse import urlencode

from h2h.odds.http import JsonTransport


@dataclass
class ApiFootballClient:
    """Fetch API-Football odds payloads with optional fixture-level TTL caching."""

    transport: JsonTransport
    api_key: str
    base_url: str = "https://v3.football.api-sports.io"
    timeout: float = 10.0
    cache_ttl_seconds: float = 0.0
    clock: Callable[[], float] = field(default=monotonic, repr=False)
    _cache: dict[int, tuple[float, Mapping[str, Any]]] = field(default_factory=dict, init=False, repr=False)

    def fetch_odds(self, *, fixture_id: int) -> Mapping[str, Any]:
        """Fetch odds for one fixture, serving a fresh cached response when enabled."""
        if fixture_id <= 0:
            raise ValueError("fixture_id must be greater than zero")
        if not self.api_key.strip():
            raise ValueError("api_key must not be empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if self.cache_ttl_seconds < 0:
            raise ValueError("cache_ttl_seconds must not be negative")

        now = self.clock()
        cached = self._cache.get(fixture_id)
        if cached is not None:
            expires_at, payload = cached
            if now < expires_at:
                return payload
            del self._cache[fixture_id]

        query = urlencode({"fixture": fixture_id})
        url = f"{self.base_url.rstrip('/')}/odds?{query}"
        payload = self.transport.get_json(
            url,
            headers={"x-apisports-key": self.api_key},
            timeout=self.timeout,
        )
        if self.cache_ttl_seconds > 0:
            self._cache[fixture_id] = (now + self.cache_ttl_seconds, payload)
        return payload

    def clear_cache(self) -> None:
        """Remove all cached fixture responses."""
        self._cache.clear()
