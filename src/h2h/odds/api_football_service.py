"""Application-facing orchestration for API-Football odds ingestion."""

from __future__ import annotations

from dataclasses import dataclass

from h2h.domain.market_snapshot import MarketSnapshot
from h2h.domain.odds import CanonicalQuote

from .api_football_client import ApiFootballClient
from .api_football_ingestion import (
    build_api_football_market_snapshots,
    ingest_api_football_odds,
)


@dataclass(frozen=True)
class ApiFootballOddsService:
    """Fetch provider data and immediately convert it to domain objects."""

    client: ApiFootballClient

    def fetch_quotes(self, *, fixture_id: int) -> tuple[CanonicalQuote, ...]:
        """Fetch and normalize all supported quotes for one fixture."""
        response = self.client.fetch_odds(fixture_id=fixture_id)
        return ingest_api_football_odds(response)

    def fetch_market_snapshots(
        self,
        *,
        fixture_id: int,
    ) -> tuple[MarketSnapshot, ...]:
        """Fetch, normalize and validate market snapshots for one fixture."""
        response = self.client.fetch_odds(fixture_id=fixture_id)
        return build_api_football_market_snapshots(response)
