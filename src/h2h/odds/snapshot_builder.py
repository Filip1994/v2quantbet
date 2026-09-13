"""Build canonical market snapshots from provider quote payloads."""

from collections.abc import Iterable, Mapping

from h2h.domain.market_snapshot import MarketSnapshot
from h2h.domain.odds import CanonicalQuote

from .provider_adapter import NormalizingProviderQuoteAdapter, ProviderQuoteAdapter


def build_market_snapshot(
    payloads: Iterable[Mapping[str, object]],
    *,
    adapter: ProviderQuoteAdapter | None = None,
) -> MarketSnapshot:
    """Adapt provider payloads and build one validated market snapshot."""
    quote_adapter = adapter or NormalizingProviderQuoteAdapter()
    quotes: tuple[CanonicalQuote, ...] = tuple(
        quote_adapter.adapt(payload) for payload in payloads
    )
    return MarketSnapshot.from_quotes(quotes)
