from datetime import UTC, datetime

import pytest

from h2h.domain.odds import Market, Selection
from h2h.domain.quote_normalizer import QuoteNormalizationError, normalize_quote

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


def test_normalize_quote_maps_supported_market_and_selection() -> None:
    quote = normalize_quote(payload())

    assert quote.fixture_id == "fixture-1"
    assert quote.bookmaker_id == 8
    assert quote.bookmaker_name == "bet365"
    assert quote.market is Market.OU_25
    assert quote.selection is Selection.OVER
    assert quote.odd == 1.95


@pytest.mark.parametrize(
    ("market", "selection", "expected_market", "expected_selection"),
    [
        ("OU_25", "UNDER", Market.OU_25, Selection.UNDER),
        ("BTTS", "YES", Market.BTTS, Selection.YES),
        ("BTTS", "NO", Market.BTTS, Selection.NO),
        ("TOTALS_2_5", "OVER", Market.OU_25, Selection.OVER),
    ],
)
def test_normalize_quote_supports_explicit_aliases(
    market, selection, expected_market, expected_selection
) -> None:
    quote = normalize_quote(payload(market=market, selection=selection))

    assert quote.market is expected_market
    assert quote.selection is expected_selection


def test_normalize_quote_rejects_unknown_market() -> None:
    with pytest.raises(QuoteNormalizationError, match="unsupported market"):
        normalize_quote(payload(market="MATCH_RESULT"))


def test_normalize_quote_rejects_unknown_selection() -> None:
    with pytest.raises(QuoteNormalizationError, match="unsupported selection"):
        normalize_quote(payload(selection="DRAW"))


def test_normalize_quote_rejects_missing_required_field() -> None:
    value = payload()
    del value["fixture_id"]

    with pytest.raises(QuoteNormalizationError, match="fixture_id"):
        normalize_quote(value)


def test_normalize_quote_rejects_unsupported_bookmaker() -> None:
    with pytest.raises(QuoteNormalizationError, match="unsupported bookmaker"):
        normalize_quote(payload(bookmaker_id=999, bookmaker_name="Unknown"))


def test_normalize_quote_rejects_bookmaker_id_name_mismatch() -> None:
    with pytest.raises(QuoteNormalizationError, match="does not match"):
        normalize_quote(payload(bookmaker_id=8, bookmaker_name="1xbet"))


def test_normalize_quote_reuses_canonical_quote_validation() -> None:
    with pytest.raises(QuoteNormalizationError, match="greater than 1.0"):
        normalize_quote(payload(odd=1.0))


def test_normalize_quote_requires_mapping() -> None:
    with pytest.raises(TypeError, match="mapping"):
        normalize_quote([])
