"""HTTP client boundary for API-Football odds data."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from h2h.odds.http import JsonTransport


@dataclass(frozen=True)
class ApiFootballClient:
    """Fetch API-Football odds payloads through an injected transport."""

    transport: JsonTransport
    api_key: str
    base_url: str = "https://v3.football.api-sports.io"
    timeout: float = 10.0

    def fetch_odds(self, *, fixture_id: int) -> Mapping[str, Any]:
        """Fetch odds for one fixture without exposing HTTP details to callers."""
        if fixture_id <= 0:
            raise ValueError("fixture_id must be greater than zero")
        if not self.api_key.strip():
            raise ValueError("api_key must not be empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        query = urlencode({"fixture": fixture_id})
        url = f"{self.base_url.rstrip('/')}/odds?{query}"
        return self.transport.get_json(
            url,
            headers={"x-apisports-key": self.api_key},
            timeout=self.timeout,
        )
