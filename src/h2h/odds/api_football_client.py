"""HTTP client boundary for API-Football odds and fixture data."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from time import monotonic
from typing import Any
from urllib.parse import urlencode

from h2h.odds.http import JsonTransport


@dataclass
class ApiFootballClient:
    """Fetch API-Football data with optional fixture-level TTL caching."""

    transport: JsonTransport
    api_key: str
    base_url: str = "https://v3.football.api-sports.io"
    timeout: float = 10.0
    cache_ttl_seconds: float = 0.0
    clock: Callable[[], float] = field(default=monotonic, repr=False)
    _cache: dict[int, tuple[float, Mapping[str, Any]]] = field(default_factory=dict, init=False, repr=False)

    def _validate(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if isinstance(self.timeout, bool) or self.timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if isinstance(self.cache_ttl_seconds, bool) or self.cache_ttl_seconds < 0:
            raise ValueError("cache_ttl_seconds must not be negative")

    @staticmethod
    def _validate_fixture_id(fixture_id: int) -> None:
        if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id <= 0:
            raise ValueError("fixture_id must be a positive integer")

    def fetch_odds(self, *, fixture_id: int) -> Mapping[str, Any]:
        """Fetch odds for one fixture, serving a fresh cached response when enabled."""
        self._validate_fixture_id(fixture_id)
        self._validate()
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
            self._cache[fixture_id] = (
                self.clock() + self.cache_ttl_seconds,
                payload,
            )
        return payload

    def fetch_fixtures(self, *, start_at: datetime, end_at: datetime) -> Mapping[str, Any]:
        """Fetch fixtures in the inclusive provider date range covering the window."""
        self._validate()
        if not isinstance(start_at, datetime) or not isinstance(end_at, datetime):
            raise TypeError("start_at and end_at must be datetime values")
        if start_at >= end_at:
            raise ValueError("start_at must be before end_at")
        query = urlencode({"from": start_at.date().isoformat(), "to": end_at.date().isoformat()})
        url = f"{self.base_url.rstrip('/')}/fixtures?{query}"
        return self.transport.get_json(
            url,
            headers={"x-apisports-key": self.api_key},
            timeout=self.timeout,
        )

    def clear_cache(self) -> None:
        """Remove all cached fixture responses."""
        self._cache.clear()
