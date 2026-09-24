"""HTTP client boundary for API-Football odds and fixture data."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from math import isfinite
from time import monotonic
from typing import Any, Final
from urllib.parse import urlencode

from h2h.odds.http import JsonTransport
from h2h.odds.budget import provider_request_category


API_FOOTBALL_BASE_URL: Final = "https://v3.football.api-sports.io"
LOGGER = logging.getLogger("quantbet.provider")


@dataclass
class ApiFootballClient:
    """Fetch API-Football data with optional fixture-level TTL caching."""

    transport: JsonTransport
    api_key: str
    base_url: str = API_FOOTBALL_BASE_URL
    timeout: float = 10.0
    cache_ttl_seconds: float = 0.0
    odds_request_category: str = "opportunity_odds"
    clock: Callable[[], float] = field(default=monotonic, repr=False)
    _cache: dict[tuple[int, int | None, int | None], tuple[float, Mapping[str, Any]]] = field(
        default_factory=dict, init=False, repr=False
    )

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

    def fetch_odds(
        self,
        *,
        fixture_id: int,
        bookmaker_id: int | None = None,
        bet_id: int | None = None,
    ) -> Mapping[str, Any]:
        """Fetch odds for one fixture, optionally pinned to bookmaker and bet type."""
        self._validate_fixture_id(fixture_id)
        if bookmaker_id is not None:
            self._validate_positive_int(bookmaker_id, "bookmaker_id")
        if bet_id is not None:
            self._validate_positive_int(bet_id, "bet_id")
        self._validate()
        now = self.clock()
        cache_key = (fixture_id, bookmaker_id, bet_id)
        cached = self._cache.get(cache_key)
        if cached is not None:
            expires_at, payload = cached
            if now < expires_at:
                return payload
            del self._cache[cache_key]

        query_values = {"fixture": fixture_id}
        if bookmaker_id is not None:
            query_values["bookmaker"] = bookmaker_id
        if bet_id is not None:
            query_values["bet"] = bet_id
        query = urlencode(query_values)
        url = f"{self.base_url.rstrip('/')}/odds?{query}"
        with provider_request_category(self.odds_request_category):
            payload = self.transport.get_json(
                url,
                headers={"x-apisports-key": self.api_key},
                timeout=self.timeout,
            )
        self._log_request("odds", payload)
        if self.cache_ttl_seconds > 0:
            self._cache[cache_key] = (
                self.clock() + self.cache_ttl_seconds,
                payload,
            )
        return payload

    def fetch_live_odds(self, *, fixture_id: int) -> Mapping[str, Any]:
        """Fetch the current API-Football in-play/live odds feed for one fixture."""
        self._validate_fixture_id(fixture_id)
        self._validate()
        query = urlencode({"fixture": fixture_id})
        url = f"{self.base_url.rstrip('/')}/odds/live?{query}"
        with provider_request_category(self.odds_request_category):
            payload = self.transport.get_json(
                url,
                headers={"x-apisports-key": self.api_key},
                timeout=self.timeout,
            )
        self._log_request("odds-live", payload)
        return payload

    def fetch_fixtures_for_date(self, *, fixture_date: date) -> Mapping[str, Any]:
        """Fetch every provider fixture on one UTC calendar date."""
        self._validate()
        if isinstance(fixture_date, datetime) or not isinstance(fixture_date, date):
            raise TypeError("fixture_date must be a date")
        query = urlencode({"date": fixture_date.isoformat()})
        url = f"{self.base_url.rstrip('/')}/fixtures?{query}"
        with provider_request_category("discovery"):
            payload = self.transport.get_json(
                url,
                headers={"x-apisports-key": self.api_key},
                timeout=self.timeout,
            )
        self._log_request("fixtures-date", payload, fixture_date=fixture_date)
        return payload

    def fetch_fixture_results(self, *, fixture_ids: tuple[int, ...]) -> Mapping[str, Any]:
        """Fetch current fixture/result records for at most twenty provider fixture IDs."""
        self._validate()
        if not fixture_ids or len(fixture_ids) > 20:
            raise ValueError("fixture_ids must contain between one and twenty IDs")
        for fixture_id in fixture_ids:
            self._validate_fixture_id(fixture_id)
        if len(set(fixture_ids)) != len(fixture_ids):
            raise ValueError("fixture_ids must not contain duplicates")
        query = urlencode({"ids": "-".join(str(value) for value in fixture_ids), "timezone": "UTC"})
        url = f"{self.base_url.rstrip('/')}/fixtures?{query}"
        with provider_request_category("results_monitoring"):
            payload = self.transport.get_json(
                url,
                headers={"x-apisports-key": self.api_key},
                timeout=self.timeout,
            )
        self._log_request("fixture-results", payload)
        return payload

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
        with provider_request_category("model_training"):
            payload = self.transport.get_json(
                url,
                headers={"x-apisports-key": self.api_key},
                timeout=self.timeout,
            )
        self._log_request("completed-fixtures", payload)
        return payload

    @staticmethod
    def _log_request(
        endpoint: str,
        payload: Mapping[str, Any],
        *,
        fixture_date: date | None = None,
    ) -> None:
        response = payload.get("response")
        response_items = len(response) if isinstance(response, list) else 0
        extra: dict[str, object] = {
            "provider_endpoint": endpoint,
            "provider_requests": 1,
            "provider_response_items": response_items,
        }
        if fixture_date is not None:
            extra["provider_fixture_date"] = fixture_date.isoformat()
        LOGGER.info(
            "provider request completed",
            extra=extra,
        )

    @staticmethod
    def _validate_positive_int(value: int, field: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{field} must be a positive integer")

    def clear_cache(self) -> None:
        """Remove all cached fixture responses."""
        self._cache.clear()
