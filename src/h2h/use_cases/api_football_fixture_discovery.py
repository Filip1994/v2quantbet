"""API-Football implementation of the provider-neutral fixture discovery port."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from h2h.odds.api_football_client import ApiFootballClient
from h2h.domain.fixture import Fixture
from h2h.use_cases.api_football_fixture_adapter import ApiFootballFixtureAdapter


class ApiFootballFixtureDiscovery:
    """Discover canonical fixtures through API-Football's fixtures endpoint."""

    def __init__(
        self,
        client: ApiFootballClient,
        adapter: ApiFootballFixtureAdapter | None = None,
    ) -> None:
        self._client = client
        self._adapter = adapter or ApiFootballFixtureAdapter()

    def discover(self, start_at: datetime, end_at: datetime) -> tuple[Fixture, ...]:
        """Fetch and adapt fixtures, retaining only kickoffs inside the requested window."""
        if start_at >= end_at:
            raise ValueError("start_at must be before end_at")
        payload = self._client.fetch_fixtures(start_at=start_at, end_at=end_at)
        if not isinstance(payload, Mapping):
            raise TypeError("API-Football fixtures response must be an object")
        errors = payload.get("errors")
        if errors:
            raise RuntimeError(f"API-Football returned errors: {errors}")
        response = payload.get("response", [])
        if not isinstance(response, list):
            raise TypeError("API-Football response must be a list")

        fixtures: list[Fixture] = []
        for item in response:
            if not isinstance(item, Mapping):
                raise TypeError("API-Football fixture item must be an object")
            fixture = self._adapter.adapt(item)
            if start_at <= fixture.kickoff_at <= end_at:
                fixtures.append(fixture)
        return tuple(fixtures)
