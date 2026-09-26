"""API-Football acquisition boundary used only by QuantLab."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from time import monotonic
from typing import Any
from urllib.parse import urlencode

from h2h.odds.budget import BudgetedJsonTransport, provider_request_category
from h2h.odds.http import JsonTransport, UrllibJsonTransport
from h2h.quantlab.budget import QuantLabRequestBudget


API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"


@dataclass
class QuantLabApiFootballClient:
    api_key: str
    budget: QuantLabRequestBudget
    transport: JsonTransport = field(default_factory=UrllibJsonTransport)
    base_url: str = API_FOOTBALL_BASE_URL
    timeout: float = 10.0
    clock: Any = field(default=monotonic, repr=False)
    _cache: dict[tuple[str, tuple[tuple[str, object], ...]], tuple[float, Mapping[str, Any]]] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("api_key must be non-empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        self.transport = BudgetedJsonTransport(self.transport, self.budget)  # type: ignore[arg-type]

    def _get(
        self,
        endpoint: str,
        params: Mapping[str, object],
        *,
        cache_ttl_seconds: float = 0.0,
    ) -> Mapping[str, Any]:
        key = (endpoint, tuple(sorted(params.items())))
        now = float(self.clock())
        cached = self._cache.get(key)
        if cached is not None and now < cached[0]:
            return cached[1]
        if cached is not None:
            del self._cache[key]
        url = f"{self.base_url.rstrip('/')}/{endpoint}?{urlencode(params)}"
        with provider_request_category("quantlab_context"):
            payload = self.transport.get_json(
                url,
                headers={"x-apisports-key": self.api_key},
                timeout=self.timeout,
            )
        if cache_ttl_seconds > 0:
            self._cache[key] = (float(self.clock()) + cache_ttl_seconds, payload)
        return payload

    def fetch_odds(self, fixture_id: int) -> Mapping[str, Any]:
        """One all-market fixture response, intentionally without bookmaker/bet filters."""
        if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id <= 0:
            raise ValueError("fixture_id must be a positive integer")
        return self._get("odds", {"fixture": fixture_id}, cache_ttl_seconds=300.0)

    def fetch_fixture(self, fixture_id: int) -> Mapping[str, Any]:
        if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id <= 0:
            raise ValueError("fixture_id must be a positive integer")
        return self._get("fixtures", {"id": fixture_id, "timezone": "UTC"}, cache_ttl_seconds=3600.0)

    def fetch_fixtures_for_date(self, fixture_date: date) -> Mapping[str, Any]:
        if isinstance(fixture_date, datetime) or not isinstance(fixture_date, date):
            raise TypeError("fixture_date must be a date")
        return self._get(
            "fixtures",
            {"date": fixture_date.isoformat(), "timezone": "UTC"},
            cache_ttl_seconds=21600.0,
        )

    def fetch_team_recent_fixtures(
        self,
        team_id: int,
        *,
        last: int = 12,
    ) -> Mapping[str, Any]:
        if isinstance(team_id, bool) or not isinstance(team_id, int) or team_id <= 0:
            raise ValueError("team_id must be a positive integer")
        if isinstance(last, bool) or not isinstance(last, int) or not 3 <= last <= 50:
            raise ValueError("last must be an integer between 3 and 50")
        return self._get(
            "fixtures",
            {"team": team_id, "last": last, "timezone": "UTC"},
            cache_ttl_seconds=21600.0,
        )

    def fetch_league_coverage(self, league_id: int, season: int) -> Mapping[str, Any]:
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (league_id, season)
        ):
            raise ValueError("league_id and season must be positive integers")
        return self._get(
            "leagues",
            {"id": league_id, "season": season},
            cache_ttl_seconds=21600.0,
        )

    def fetch_standings(self, league_id: int, season: int) -> Mapping[str, Any]:
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in (league_id, season)):
            raise ValueError("league_id and season must be positive integers")
        return self._get(
            "standings",
            {"league": league_id, "season": season},
            cache_ttl_seconds=1800.0,
        )

    def fetch_statistics(self, fixture_id: int) -> Mapping[str, Any]:
        if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id <= 0:
            raise ValueError("fixture_id must be a positive integer")
        return self._get(
            "fixtures/statistics",
            {"fixture": fixture_id},
            cache_ttl_seconds=86400.0,
        )
