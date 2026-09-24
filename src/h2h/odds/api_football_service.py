"""Application-facing orchestration for API-Football odds ingestion."""

from __future__ import annotations

from dataclasses import dataclass

from h2h.domain.fixture_identity import (
    ResolvedFixtureIdentity,
    api_football_provider_fixture_id,
)
from h2h.domain.market_snapshot import MarketSnapshot
from h2h.domain.odds import CanonicalQuote, Market

from .api_football_client import ApiFootballClient
from .api_football_adapter import api_football_bet_id_for_market
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
        market: Market | None = None,
    ) -> tuple[CanonicalQuote, ...]:
        """Fetch and normalize quotes, optionally pinned to one canonical market."""
        provider_fixture_id = api_football_provider_fixture_id(fixture_identity)
        response = self.client.fetch_odds(
            fixture_id=provider_fixture_id,
            bookmaker_id=bookmaker_id,
            bet_id=None if market is None else api_football_bet_id_for_market(market),
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
        response = self.client.fetch_odds(fixture_id=provider_fixture_id, bet_id=None)
        return build_api_football_market_snapshots(
            response,
            fixture_identity=fixture_identity,
        )
