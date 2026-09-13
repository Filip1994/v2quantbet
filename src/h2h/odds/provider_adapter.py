"""Provider adapter contracts for translating external odds payloads."""

from collections.abc import Mapping
from typing import Protocol

from h2h.domain.odds import CanonicalQuote
from h2h.domain.quote_normalizer import normalize_quote


class ProviderQuoteAdapter(Protocol):
    """Translate one provider payload into a provider-neutral canonical quote."""

    def adapt(self, payload: Mapping[str, object]) -> CanonicalQuote:
        """Return a validated canonical quote or raise a normalization error."""
        ...


class NormalizingProviderQuoteAdapter:
    """Default adapter for payloads already expressed in the neutral contract."""

    def adapt(self, payload: Mapping[str, object]) -> CanonicalQuote:
        """Normalize and validate one provider payload."""
        return normalize_quote(payload)
