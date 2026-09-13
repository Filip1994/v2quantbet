from datetime import UTC, datetime

import pytest

from h2h.domain.odds import Market, Selection
from h2h.odds import build_market_snapshot

OBSERVED_AT = datetime(2026, 9, 13, 10, 0, tzinfo=UTC)


def payload(selection: str, *, market: str = "OU_25") -> dict[str, object]:
    return {
        "fixture_id": "fixture-1",
        "bookmaker_id": 8,
        "bookmaker_name": "Example Bookmaker",
        "market": market,
        "selection": selection,
        "odd": 1.95,
        "observed_at": OBSERVED_AT,
        "source": "provider-x",
    }


def test_build_market_snapshot_adapts_all_payloads() -> None:
    snapshot = build_market_snapshot((payload("OVER"), payload("UNDER")))

    assert snapshot.fixture_id == "fixture-1"
    assert snapshot.market is Market.OU_25
    assert snapshot.quote_for(Selection.OVER).odd == 1.95
    assert snapshot.quote_for(Selection.UNDER).odd == 1.95


def test_build_market_snapshot_rejects_incomplete_market() -> None:
    with pytest.raises(ValueError, match="exactly"):
        build_market_snapshot((payload("OVER"),))


def test_build_market_snapshot_rejects_empty_payloads() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        build_market_snapshot(())
