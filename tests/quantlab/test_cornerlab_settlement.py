from datetime import UTC, datetime

from h2h.quantlab.corner_lab.settlement import settle_corner_shadow_bet


NOW = datetime(2026, 9, 27, 1, 0, tzinfo=UTC)


def _row(*, selection="OVER", line=9.5, home=6, away=5, odds=2.10):
    return {
        "shadow_bet_id": "quantlab-shadow-v1:" + "a" * 64,
        "fixture_id": "api-football:123",
        "market_key": "TOTAL_CORNERS",
        "selection": selection,
        "line": line,
        "odds": odds,
        "stake_minor": 10_000,
        "result_classification": "PLAYED_SETTLEABLE",
        "provider_status": "FT",
        "statistics_observation_id": "stats:123",
        "statistics_available_at": NOW,
        "home_corner_kicks": home,
        "away_corner_kicks": away,
    }


def test_corner_settlement_over_win_uses_actual_corner_total():
    settlement = settle_corner_shadow_bet(_row(), settled_at=NOW)

    assert settlement is not None
    assert settlement.outcome == "WIN"
    assert settlement.pnl_minor == 11_000
    assert settlement.result_detail["actual_total_corners"] == 11
    assert settlement.result_detail["line"] == 9.5


def test_corner_settlement_under_loss():
    settlement = settle_corner_shadow_bet(
        _row(selection="UNDER", line=10.5, home=6, away=5),
        settled_at=NOW,
    )

    assert settlement is not None
    assert settlement.outcome == "LOSS"
    assert settlement.pnl_minor == -10_000


def test_corner_settlement_non_played_is_void():
    row = _row()
    row.update(
        {
            "result_classification": "NON_PLAYED_VOIDABLE",
            "home_corner_kicks": None,
            "away_corner_kicks": None,
        }
    )

    settlement = settle_corner_shadow_bet(row, settled_at=NOW)

    assert settlement is not None
    assert settlement.outcome == "VOID"
    assert settlement.pnl_minor == 0
