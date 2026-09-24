"""Application-facing orchestration for API-Football odds ingestion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from h2h.domain.fixture_identity import (
    ResolvedFixtureIdentity,
    api_football_provider_fixture_id,
)
from h2h.domain.market_snapshot import MarketSnapshot
from h2h.domain.odds import CanonicalQuote, Market

from .api_football_client import ApiFootballClient
from .api_football_adapter import api_football_bet_id_for_market
from .api_football_live import LiveMarketQuote, parse_api_football_live_quotes
from .api_football_ingestion import (
    build_api_football_market_snapshots,
    ingest_api_football_odds,
)


@dataclass(frozen=True)
class ScopedOddsResult:
    quotes_by_fixture: Mapping[str, tuple[CanonicalQuote, ...]]
    provider_requests: int


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

    def fetch_scope_quotes(
        self,
        *,
        league_id: int,
        season: int,
        fixture_date: date,
        fixture_identities: tuple[ResolvedFixtureIdentity, ...],
        max_pages: int = 20,
    ) -> ScopedOddsResult:
        """Discover supported odds once for a league/date scope and fan them out by fixture."""
        if not fixture_identities:
            return ScopedOddsResult({}, 0)
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")

        identity_by_provider = {
            api_football_provider_fixture_id(identity): identity
            for identity in fixture_identities
        }
        if len(identity_by_provider) != len(fixture_identities):
            raise ValueError("fixture_identities must not contain duplicate provider fixtures")

        quotes_by_fixture: dict[str, list[CanonicalQuote]] = {
            identity.fixture_id: [] for identity in fixture_identities
        }
        requests = 0
        page = 1
        while True:
            payload = self.client.fetch_odds_for_scope(
                league_id=league_id,
                season=season,
                fixture_date=fixture_date,
                page=page,
            )
            requests += 1
            errors = payload.get("errors")
            if errors:
                raise RuntimeError(f"API-Football returned odds errors: {errors}")
            response = payload.get("response", [])
            if not isinstance(response, list):
                raise TypeError("API-Football odds response must contain a list")
            for record in response:
                if not isinstance(record, Mapping):
                    raise TypeError("API-Football odds response record must be a mapping")
                fixture = record.get("fixture")
                if not isinstance(fixture, Mapping):
                    raise TypeError("API-Football odds fixture must be a mapping")
                provider_fixture_id = fixture.get("id")
                if (
                    isinstance(provider_fixture_id, bool)
                    or not isinstance(provider_fixture_id, int)
                    or provider_fixture_id <= 0
                ):
                    raise TypeError("API-Football odds fixture.id must be a positive integer")
                identity = identity_by_provider.get(provider_fixture_id)
                if identity is None:
                    continue
                single_response = {"errors": [], "response": [record]}
                quotes_by_fixture[identity.fixture_id].extend(
                    ingest_api_football_odds(
                        single_response,
                        fixture_identity=identity,
                        bookmaker_id=None,
                    )
                )

            paging = payload.get("paging", {})
            if not isinstance(paging, Mapping):
                raise TypeError("API-Football odds paging must be a mapping")
            current = paging.get("current", page)
            total = paging.get("total", current)
            if (
                isinstance(current, bool)
                or not isinstance(current, int)
                or current <= 0
                or isinstance(total, bool)
                or not isinstance(total, int)
                or total <= 0
            ):
                raise TypeError("API-Football odds paging values must be positive integers")
            if current >= total:
                break
            if requests >= max_pages:
                raise RuntimeError("API-Football odds scope exceeded pagination bound")
            page = current + 1

        return ScopedOddsResult(
            {
                fixture_id: tuple(quotes)
                for fixture_id, quotes in quotes_by_fixture.items()
            },
            requests,
        )

    def fetch_live_quotes(
        self,
        *,
        fixture_identity: ResolvedFixtureIdentity,
    ) -> tuple[LiveMarketQuote, ...]:
        """Fetch API-Football live-market quotes for freshness corroboration."""
        provider_fixture_id = api_football_provider_fixture_id(fixture_identity)
        response = self.client.fetch_live_odds(fixture_id=provider_fixture_id)
        return parse_api_football_live_quotes(response, fixture_id=provider_fixture_id)

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
