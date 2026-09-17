"""Application-facing orchestration for API-Football odds ingestion."""

from __future__ import annotations

from dataclasses import dataclass

from h2h.domain.fixture_identity import (
    ResolvedFixtureIdentity,
    api_football_provider_fixture_id,
)
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

    def fetch_quotes(
        self,
        *,
        fixture_identity: ResolvedFixtureIdentity,
        bookmaker_id: int | None = None,
    ) -> tuple[CanonicalQuote, ...]:
        """Fetch and normalize all supported quotes for one fixture."""
        provider_fixture_id = api_football_provider_fixture_id(fixture_identity)
        response = self.client.fetch_odds(
            fixture_id=provider_fixture_id, bookmaker_id=bookmaker_id
        )
        return ingest_api_football_odds(
            response,
            fixture_identity=fixture_identity,
            bookmaker_id=bookmaker_id,
        )

    def fetch_market_snapshots(
        self,
        *,
        fixture_identity: ResolvedFixtureIdentity,
    ) -> tuple[MarketSnapshot, ...]:
        """Fetch, normalize and validate market snapshots for one fixture."""
        provider_fixture_id = api_football_provider_fixture_id(fixture_identity)
        response = self.client.fetch_odds(fixture_id=provider_fixture_id)
        return build_api_football_market_snapshots(
            response,
            fixture_identity=fixture_identity,
        )
