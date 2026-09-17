"""Flatten API-Football odds responses into canonical quote inputs."""

from collections.abc import Iterator, Mapping
from typing import Any

from h2h.domain.market_snapshot import MarketSnapshot
from h2h.domain.fixture_identity import (
    ResolvedFixtureIdentity,
    api_football_provider_fixture_id,
)
from h2h.domain.odds import CanonicalQuote
from h2h.domain.quote_normalizer import QuoteNormalizationError

from .api_football_adapter import ApiFootballQuoteAdapter
from .quote_deduplication import deduplicate_quotes


def iter_api_football_quote_payloads(
    response: Mapping[str, Any],
    *,
    fixture_identity: ResolvedFixtureIdentity,
    bookmaker_id: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one flattened payload for each bookmaker/bet/value combination.

    Every response record's fixture identity is validated before any quote is
    yielded. This prevents empty or unsupported records from bypassing the
    requested-fixture boundary and prevents partially accepting mixed-fixture
    responses.

    Unsupported or incomplete branches are skipped. The provider-specific
    response shape remains isolated in this ingestion layer; the resulting
    payloads are consumed by ``ApiFootballQuoteAdapter``.
    """
    if not isinstance(response, Mapping):
        raise TypeError("API-Football odds response must be an object")

    errors = response.get("errors")
    if errors:
        raise RuntimeError(f"API-Football returned errors: {errors}")

    fixtures = response.get("response", [])
    if not isinstance(fixtures, list):
        raise TypeError("API-Football odds response must contain a list")

    requested_fixture_id = api_football_provider_fixture_id(fixture_identity)
    validated_fixtures: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for index, fixture in enumerate(fixtures):
        try:
            if not isinstance(fixture, Mapping):
                raise TypeError("response record must be a mapping")
            fixture_data = fixture.get("fixture")
            if not isinstance(fixture_data, Mapping):
                raise TypeError("fixture must be a mapping")
            response_fixture_id = fixture_data.get("id")
            if (
                isinstance(response_fixture_id, bool)
                or not isinstance(response_fixture_id, int)
                or response_fixture_id <= 0
            ):
                raise TypeError("fixture.id must be a positive integer")
            if response_fixture_id != requested_fixture_id:
                raise ValueError(
                    "fixture.id does not match the requested API-Football fixture"
                )
        except (TypeError, ValueError) as exc:
            raise QuoteNormalizationError(
                f"invalid API-Football odds response record at index {index}: {exc}"
            ) from exc
        validated_fixtures.append((fixture, fixture_data))

    for fixture, fixture_data in validated_fixtures:
        bookmakers = fixture.get("bookmakers", [])
        if not isinstance(bookmakers, list):
            continue

        for bookmaker in bookmakers:
            if not isinstance(bookmaker, Mapping):
                continue
            if bookmaker_id is not None and bookmaker.get("id") != bookmaker_id:
                continue
            bets = bookmaker.get("bets", [])
            if not isinstance(bets, list):
                continue

            for bet in bets:
                if not isinstance(bet, Mapping):
                    continue
                if bet.get("id") not in (5, 8):
                    continue
                values = bet.get("values", [])
                if not isinstance(values, list):
                    continue

                for value in values:
                    if not isinstance(value, Mapping):
                        continue
                    selection = value.get("value")
                    if not isinstance(selection, str):
                        continue
                    normalized_selection = selection.strip().upper()
                    if bet.get("id") == 5 and normalized_selection not in {
                        "OVER 2.5",
                        "UNDER 2.5",
                    }:
                        continue
                    if bet.get("id") == 8 and normalized_selection not in {"YES", "NO"}:
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
    fixture_identity: ResolvedFixtureIdentity,
    adapter: ApiFootballQuoteAdapter | None = None,
    bookmaker_id: int | None = None,
) -> tuple[CanonicalQuote, ...]:
    """Convert a complete API-Football odds response into canonical quotes."""
    quote_adapter = adapter or ApiFootballQuoteAdapter()
    return deduplicate_quotes(
        quote_adapter.adapt(payload, fixture_identity=fixture_identity)
        for payload in iter_api_football_quote_payloads(
            response,
            fixture_identity=fixture_identity,
            bookmaker_id=bookmaker_id,
        )
    )


def build_api_football_market_snapshots(
    response: Mapping[str, Any],
    *,
    fixture_identity: ResolvedFixtureIdentity,
    adapter: ApiFootballQuoteAdapter | None = None,
    bookmaker_id: int | None = None,
) -> tuple[MarketSnapshot, ...]:
    """Build validated snapshots grouped by fixture, bookmaker, market and time."""
    quotes = ingest_api_football_odds(
        response,
        fixture_identity=fixture_identity,
        adapter=adapter,
        bookmaker_id=bookmaker_id,
    )
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
