"""Flatten API-Football odds responses into canonical quote inputs."""

from collections.abc import Iterator, Mapping
from typing import Any

from h2h.domain.market_snapshot import MarketSnapshot
from h2h.domain.odds import CanonicalQuote

from .api_football_adapter import ApiFootballQuoteAdapter
from .quote_deduplication import deduplicate_quotes


def iter_api_football_quote_payloads(
    response: Mapping[str, Any],
) -> Iterator[dict[str, Any]]:
    """Yield one flattened payload for each bookmaker/bet/value combination.

    Unsupported or incomplete branches are skipped. The provider-specific
    response shape remains isolated in this ingestion layer; the resulting
    payloads are consumed by ``ApiFootballQuoteAdapter``.
    """
    fixtures = response.get("response", [])
    if not isinstance(fixtures, list):
        return

    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            continue
        fixture_data = fixture.get("fixture")
        bookmakers = fixture.get("bookmakers", [])
        if not isinstance(fixture_data, Mapping) or not isinstance(bookmakers, list):
            continue

        for bookmaker in bookmakers:
            if not isinstance(bookmaker, Mapping):
                continue
            bets = bookmaker.get("bets", [])
            if not isinstance(bets, list):
                continue

            for bet in bets:
                if not isinstance(bet, Mapping):
                    continue
                values = bet.get("values", [])
                if not isinstance(values, list):
                    continue

                for value in values:
                    if not isinstance(value, Mapping):
                        continue
                    yield {
                        "fixture": fixture_data,
                        "bookmaker": {
                            "id": bookmaker.get("id"),
                            "name": bookmaker.get("name"),
                        },
                        "bet": {
                            "id": bet.get("id"),
                            "name": bet.get("name"),
                        },
                        "value": dict(value),
                        "update": value.get("update")
                        or bookmaker.get("update")
                        or fixture.get("update"),
                    }


def ingest_api_football_odds(
    response: Mapping[str, Any],
    *,
    adapter: ApiFootballQuoteAdapter | None = None,
) -> tuple[CanonicalQuote, ...]:
    """Convert a complete API-Football odds response into canonical quotes."""
    quote_adapter = adapter or ApiFootballQuoteAdapter()
    return deduplicate_quotes(
        quote_adapter.adapt(payload)
        for payload in iter_api_football_quote_payloads(response)
    )


def build_api_football_market_snapshots(
    response: Mapping[str, Any],
    *,
    adapter: ApiFootballQuoteAdapter | None = None,
) -> tuple[MarketSnapshot, ...]:
    """Build validated snapshots grouped by fixture, bookmaker, market and time."""
    quotes = ingest_api_football_odds(response, adapter=adapter)
    groups: dict[tuple[str, int, object, object], list[CanonicalQuote]] = {}
    for quote in quotes:
        key = (
            quote.fixture_id,
            quote.bookmaker_id,
            quote.market,
            quote.observed_at,
        )
        groups.setdefault(key, []).append(quote)

    return tuple(MarketSnapshot.from_quotes(group) for group in groups.values())
