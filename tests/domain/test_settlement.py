from datetime import UTC, datetime
from decimal import Decimal

import pytest

from h2h.domain.fixture_result import ApiFootballSettlementResultNormalizer
from h2h.domain.odds import Market, Selection
from h2h.domain.settlement import (
    SettlementOutcome,
    realized_clv_ppm,
    settle_market,
    settlement_amounts,
)
from tests.domain.test_fixture_result import payload


NOW = datetime(2026, 9, 16, 15, tzinfo=UTC)


def result(home, away):
    return ApiFootballSettlementResultNormalizer().normalize(
        payload(goals=(home, away), fulltime=(home, away)),
        fixture_id="api-football:42",
        acquired_at=NOW,
    )


@pytest.mark.parametrize(
    ("market", "selection", "score", "expected"),
    [
        (Market.OU_25, Selection.OVER, (1, 1), SettlementOutcome.LOSS),
        (Market.OU_25, Selection.OVER, (2, 1), SettlementOutcome.WIN),
        (Market.OU_25, Selection.UNDER, (1, 1), SettlementOutcome.WIN),
        (Market.OU_25, Selection.UNDER, (2, 1), SettlementOutcome.LOSS),
        (Market.BTTS, Selection.YES, (1, 1), SettlementOutcome.WIN),
        (Market.BTTS, Selection.YES, (1, 0), SettlementOutcome.LOSS),
        (Market.BTTS, Selection.NO, (0, 4), SettlementOutcome.WIN),
        (Market.BTTS, Selection.NO, (1, 1), SettlementOutcome.LOSS),
    ],
)
def test_all_supported_market_rules_have_no_push(market, selection, score, expected):
    assert settle_market(market, selection, result(*score)) is expected


def test_void_status_voids_every_supported_selection():
    void = ApiFootballSettlementResultNormalizer().normalize(
        payload("CANC", goals=(None, None), fulltime=(None, None)),
        fixture_id="api-football:42",
        acquired_at=NOW,
    )
    assert settle_market(Market.OU_25, Selection.OVER, void) is SettlementOutcome.VOID
    assert settle_market(Market.BTTS, Selection.NO, void) is SettlementOutcome.VOID


def test_half_up_money_and_outcome_effects():
    win = settlement_amounts(
        stake_minor=101, entry_odd_decimal=Decimal("1.5"), outcome=SettlementOutcome.WIN
    )
    assert (win.gross_return_minor, win.realized_pnl_minor, win.ledger_delta_minor) == (152, 51, 152)
    loss = settlement_amounts(
        stake_minor=101, entry_odd_decimal=Decimal(2), outcome=SettlementOutcome.LOSS
    )
    assert (loss.gross_return_minor, loss.realized_pnl_minor, loss.ledger_delta_minor) == (0, -101, 0)
    void = settlement_amounts(
        stake_minor=101, entry_odd_decimal=Decimal(2), outcome=SettlementOutcome.VOID
    )
    assert (void.gross_return_minor, void.realized_pnl_minor, void.ledger_delta_minor) == (101, 0, 101)


@pytest.mark.parametrize(
    ("entry", "closing", "expected"),
    [
        ("2", "2", 0),
        ("2.1", "2", 50_000),
        ("1.9", "2", -50_000),
        ("1.5", "2", -250_000),
    ],
)
def test_realized_clv_sign_and_precision(entry, closing, expected):
    assert realized_clv_ppm(Decimal(entry), Decimal(closing)) == expected
