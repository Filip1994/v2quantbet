"""HTTP client boundary for API-Football odds and fixture data."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from time import monotonic
from typing import Any, Final
from urllib.parse import urlencode

from h2h.odds.http import JsonTransport


API_FOOTBALL_BASE_URL: Final = "https://v3.football.api-sports.io"


@dataclass
class ApiFootballClient:
    """Fetch API-Football data with optional fixture-level TTL caching."""

    transport: JsonTransport
    api_key: str
    base_url: str = API_FOOTBALL_BASE_URL
    timeout: float = 10.0
    cache_ttl_seconds: float = 0.0
    clock: Callable[[], float] = field(default=monotonic, repr=False)
    _cache: dict[int, tuple[float, Mapping[str, Any]]] = field(default_factory=dict, init=False, repr=False)

    def _validate(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or not isfinite(self.timeout)
            or self.timeout <= 0
        ):
            raise ValueError("timeout must be a positive finite number")
        if (
            isinstance(self.cache_ttl_seconds, bool)
            or not isinstance(self.cache_ttl_seconds, (int, float))
            or not isfinite(self.cache_ttl_seconds)
            or self.cache_ttl_seconds < 0
        ):
            raise ValueError("cache_ttl_seconds must be a non-negative finite number")

    @staticmethod
    def _validate_fixture_id(fixture_id: int) -> None:
        if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id <= 0:
            raise ValueError("fixture_id must be a positive integer")

    @staticmethod
    def _validate_datetime(value: datetime, field: str) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field} must be timezone-aware")

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
        self._validate_datetime(start_at, "start_at")
        self._validate_datetime(end_at, "end_at")
        if start_at >= end_at:
            raise ValueError("start_at must be before end_at")
        query = urlencode({"from": start_at.date().isoformat(), "to": end_at.date().isoformat()})
        url = f"{self.base_url.rstrip('/')}/fixtures?{query}"
        return self.transport.get_json(
            url,
            headers={"x-apisports-key": self.api_key},
            timeout=self.timeout,
        )

    def fetch_completed_fixtures(
        self,
        *,
        league_id: int,
        season: int,
        start_at: datetime,
        end_at: datetime,
    ) -> Mapping[str, Any]:
        """Fetch one FT-only league/season slice using UTC calendar boundaries."""
        self._validate()
        self._validate_positive_int(league_id, "league_id")
        self._validate_positive_int(season, "season")
        if not isinstance(start_at, datetime) or not isinstance(end_at, datetime):
            raise TypeError("start_at and end_at must be datetime values")
        self._validate_datetime(start_at, "start_at")
        self._validate_datetime(end_at, "end_at")
        start_utc = start_at.astimezone(UTC)
        end_utc = end_at.astimezone(UTC)
        if start_utc >= end_utc:
            raise ValueError("start_at must be before end_at")

        query = urlencode(
            {
                "league": league_id,
                "season": season,
                "from": start_utc.date().isoformat(),
                "to": end_utc.date().isoformat(),
                "status": "FT",
                "timezone": "UTC",
            }
        )
        url = f"{self.base_url.rstrip('/')}/fixtures?{query}"
        return self.transport.get_json(
            url,
            headers={"x-apisports-key": self.api_key},
            timeout=self.timeout,
        )

    @staticmethod
    def _validate_positive_int(value: int, field: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{field} must be a positive integer")

    def clear_cache(self) -> None:
        """Remove all cached fixture responses."""
        self._cache.clear()
