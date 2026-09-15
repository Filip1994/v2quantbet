from datetime import UTC, datetime

import pytest

from h2h.domain.odds import Market, Selection
from h2h.odds import NormalizingProviderQuoteAdapter

OBSERVED_AT = datetime(2026, 9, 13, 10, 0, tzinfo=UTC)


def payload(**overrides):
    value = {
        "fixture_id": "fixture-1",
        "bookmaker_id": 8,
        "bookmaker_name": "Bet365",
        "market": "OU_25",
        "selection": "OVER",
        "odd": 1.95,
        "observed_at": OBSERVED_AT,
        "source": "provider-x",
    }
    value.update(overrides)
    return value


def test_normalizing_adapter_returns_canonical_quote() -> None:
    quote = NormalizingProviderQuoteAdapter().adapt(payload())

    assert quote.fixture_id == "fixture-1"
    assert quote.market is Market.OU_25
    assert quote.selection is Selection.OVER
    assert quote.odd == 1.95


def test_normalizing_adapter_preserves_normalizer_validation() -> None:
    with pytest.raises(ValueError, match="greater than 1.0"):
        NormalizingProviderQuoteAdapter().adapt(payload(odd=1.0))
